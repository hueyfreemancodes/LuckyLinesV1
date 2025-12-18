
import sys
import os
import logging
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, TeamGameOffenseStats, Game, PlayerSeasonStats, Player, Team, VegasLine, TeamGameDefenseStats
from app.models.projections.xgboost_model import XGBoostModel
from app.services.feature_engineering import FeatureEngineering
from app.services.opponent_defense_features import calculate_opponent_defense_features

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Standard mapping for team abbreviations
ABBR_MAP = {
    'JAC': 'JAX', 'STL': 'LAR', 'SL': 'LAR', 'SD': 'LAC', 'SDG': 'LAC',
    'OAK': 'LV', 'LVR': 'LV', 'LAS': 'LV', 'TAM': 'TB', 'TBB': 'TB',
    'KAN': 'KC', 'KNC': 'KC', 'NWE': 'NE', 'NOR': 'NO', 'SFO': 'SF',
    'GNB': 'GB', 'GRE': 'GB', 'WSH': 'WAS', 'HST': 'HOU', 'CLV': 'CLE',
    'BLT': 'BAL', 'ARZ': 'ARI', 'LA': 'LAR'
}

def normalize_abbr(abbr):
    return ABBR_MAP.get(abbr, abbr) if abbr else None

def fetch_data(db):
    logger.info("Fetching raw data...")
    # Fetch PlayerGameStats with Position
    stats = db.query(PlayerGameStats, Player.position).join(Player).filter(
        PlayerGameStats.fantasy_points_ppr.isnot(None)
    ).all()
    
    data = [{
        **{c.name: getattr(s, c.name) for c in PlayerGameStats.__table__.columns},
        'position': pos
    } for s, pos in stats]
    
    # Pre-fetch lookups
    games = {g.id: g for g in db.query(Game).all()}
    teams = {t.id: t.abbreviation for t in db.query(Team).all()}
    season_stats = {(s.player_id, s.season): s for s in db.query(PlayerSeasonStats).all()}
    vegas = {v.game_id: v for v in db.query(VegasLine).all()}
    
    return data, games, teams, season_stats, vegas

def enrich_data(data, games, teams, season_stats, vegas):
    for row in data:
        gid = row.get('game_id')
        game = games.get(gid)
        
        # Weather
        row['forecast_wind_speed'] = game.forecast_wind_speed if game else 0
        row['forecast_temp_low'] = game.forecast_temp_low if game else 50
        row['forecast_humidity'] = game.forecast_humidity if game else 0
        
        # Vegas
        v = vegas.get(gid)
        row['vegas_total'] = v.total_points if v else 0.0
        row['vegas_spread'] = v.spread if v else 0.0
        
        # History
        prev = season_stats.get((row['player_id'], row['season'] - 1))
        row['vorp_last_season'] = prev.vorp if prev and prev.vorp else 0.0
        row['ppg_last_season'] = (prev.fantasy_points_ppr / prev.games_played) if (prev and prev.games_played) else 0.0
        
        # Opponent
        row['opponent'] = None
        if game:
            p_team = row.get('team')
            home = teams.get(game.home_team_id)
            away = teams.get(game.away_team_id)
            
            if p_team == home:
                row['opponent'] = normalize_abbr(away)
            elif p_team == away: 
                row['opponent'] = normalize_abbr(home)

    return pd.DataFrame(data)

def main():
    db = SessionLocal()
    try:
        raw_data, games, teams, season_stats, vegas = fetch_data(db)
        df = enrich_data(raw_data, games, teams, season_stats, vegas)
        
        # Defense Stats
        def_stats = db.query(TeamGameDefenseStats).all()
        def_df = pd.DataFrame([{
            'team': normalize_abbr(d.team_name),
            'season': d.season,
            'week': d.week,
            'points_allowed': d.points_allowed,
            'yards_allowed': d.yards_allowed,
            'sacks': d.sacks,
            'interceptions': d.interceptions,
            'fumbles_recovered': d.fumbles_recovered
        } for d in def_stats])
        
        team_off = pd.DataFrame([{
            'team_name': t.team_name, 'season': t.season, 'week': t.week,
            'pass_attempts': t.pass_attempts, 'rush_attempts': t.rush_attempts
        } for t in db.query(TeamGameOffenseStats).all()])
        
        # Filter valid rows
        df = df[df['opponent'].notna()]
        df = calculate_opponent_defense_features(df, def_df)
        df = FeatureEngineering.add_vegas_implied(df)
        
        # Clean target
        target = 'fantasy_points_ppr'
        df[target] = pd.to_numeric(df[target], errors='coerce')
        df = df.dropna(subset=[target])
        df = df[df[target] >= 1.0] # Ignore noise
        
        logger.info(f"Training on {len(df)} rows...")
        
        # Train/Test
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
        
        model = XGBoostModel()
        metrics = model.train(train_df, team_off)
        
        # Validate
        train_preds = model.predict(train_df, team_off)
        test_preds = model.predict(test_df, team_off)
        
        train_mae = (train_df[target] - train_preds).abs().mean()
        test_mae = (test_df[target] - test_preds).abs().mean()
        ratio = test_mae / train_mae if train_mae > 0 else 1.0
        
        logger.info(f"Results - MAE: {test_mae:.2f}, Train MAE: {train_mae:.2f} (Ratio: {ratio:.2f})")
        
        if ratio > 1.15:
            logger.warning("Potential overfitting defined (ratio > 1.15).")
            
        model.save("nfl_xgboost_model.joblib")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
