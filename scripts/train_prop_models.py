import sys
import os
import logging
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, TeamGameOffenseStats, Game, PlayerSeasonStats, Player, Team, VegasLine
from app.models.projections.xgboost_model import XGBoostModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def train_model_for_target(target_col, position_filter=None, model_filename=None):
    logger.info(f"\n=== Training Model for {target_col} ===")
    db = SessionLocal()
    try:
        # Fetch PlayerGameStats with Player join
        stats_query = db.query(
            PlayerGameStats,
            Player.position
        ).join(
            Player, PlayerGameStats.player_id == Player.id
        ).filter(
            getattr(PlayerGameStats, target_col).isnot(None)
        )
        
        if position_filter:
            stats_query = stats_query.filter(Player.position.in_(position_filter))
            
        stats_with_position = stats_query.all()
        stats_data = [{
            **{c.name: getattr(stat, c.name) for c in PlayerGameStats.__table__.columns},
            'position': position
        } for stat, position in stats_with_position]
        
        if not stats_data:
            logger.warning(f"No data found for {target_col}")
            return

        # Fetch Teams
        teams = db.query(Team).all()
        team_id_map = {t.id: t.abbreviation for t in teams}
        
        # Abbreviation Map
        ABBR_MAP = {
            'JAC': 'JAX', 'STL': 'LAR', 'SL': 'LAR', 'SD': 'LAC', 'SDG': 'LAC',
            'OAK': 'LV', 'LVR': 'LV', 'LAS': 'LV', 'TAM': 'TB', 'TBB': 'TB',
            'KAN': 'KC', 'KNC': 'KC', 'NWE': 'NE', 'NOR': 'NO', 'SFO': 'SF',
            'GNB': 'GB', 'GRE': 'GB', 'WSH': 'WAS', 'HST': 'HOU', 'CLV': 'CLE',
            'BLT': 'BAL', 'ARZ': 'ARI', 'LA': 'LAR'
        }
        def normalize_abbr(abbr):
            return ABBR_MAP.get(abbr, abbr) if abbr else None
            
        # Fetch Games & Vegas Lines
        games = db.query(Game).all()
        game_map = {g.id: g for g in games}
        
        vegas_lines = db.query(VegasLine).all()
        vegas_map = {vl.game_id: vl for vl in vegas_lines}
        
        # Fetch Season Stats
        season_stats = db.query(PlayerSeasonStats).all()
        season_stats_map = {(s.player_id, s.season): s for s in season_stats}
        
        # Enrich Data
        for row in stats_data:
            game_id = row.get('game_id')
            game = game_map.get(game_id)
            
            # Weather
            row['forecast_wind_speed'] = game.forecast_wind_speed if game else 0
            row['forecast_temp_high'] = game.forecast_temp_high if game else 70
            row['forecast_temp_low'] = game.forecast_temp_low if game else 50
            row['forecast_humidity'] = game.forecast_humidity if game else 0
            
            # Vegas
            v_line = vegas_map.get(game_id)
            row['vegas_total'] = v_line.total_points if v_line else 0.0
            row['vegas_spread'] = v_line.spread if v_line else 0.0
            
            # Season Stats
            prev_season_key = (row['player_id'], row['season'] - 1)
            prev_stats = season_stats_map.get(prev_season_key)
            row['vorp_last_season'] = prev_stats.vorp if prev_stats and prev_stats.vorp is not None else 0.0
            row['ppg_last_season'] = (prev_stats.fantasy_points_ppr / prev_stats.games_played) if (prev_stats and prev_stats.games_played) else 0.0
            
            # Opponent
            row['opponent'] = None
            if game:
                player_team = row.get('team')
                home_team = team_id_map.get(game.home_team_id)
                away_team = team_id_map.get(game.away_team_id)
                
                if player_team == home_team:
                    row['opponent'] = normalize_abbr(away_team)
                elif player_team == away_team:
                    row['opponent'] = normalize_abbr(home_team)

        df = pd.DataFrame(stats_data)
        
        # Team Stats
        team_stats = db.query(TeamGameOffenseStats).all()
        team_stats_df = pd.DataFrame([{
            'team_name': ts.team_name, 'season': ts.season, 'week': ts.week,
            'pass_attempts': ts.pass_attempts, 'rush_attempts': ts.rush_attempts
        } for ts in team_stats])
        
        # Defense Stats
        from app.models.models import TeamGameDefenseStats
        defense_stats = db.query(TeamGameDefenseStats).all()
        defense_stats_df = pd.DataFrame([{
            'team': normalize_abbr(ds.team_name), 'season': ds.season, 'week': ds.week,
            'points_allowed': ds.points_allowed, 'yards_allowed': ds.yards_allowed,
            'sacks': ds.sacks, 'interceptions': ds.interceptions, 'fumbles_recovered': ds.fumbles_recovered
        } for ds in defense_stats])
        
        # Filter valid opponent
        df = df[df['opponent'].notna()]
        
        # Calculate Defense Features
        from app.services.opponent_defense_features import calculate_opponent_defense_features
        df = calculate_opponent_defense_features(df, defense_stats_df)
        
        # Calculate Implied Totals
        from app.services.feature_engineering import FeatureEngineering
        df = FeatureEngineering.calculate_implied_totals(df)
        
        # Ensure target column is numeric and drop NaNs
        df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
        before_count = len(df)
        df = df.dropna(subset=[target_col])
        
        # Apply specific filters based on target
        if target_col == 'passing_yards':
            # Filter out QBs with < 5 attempts (mop-up duty/injury)
            if 'pass_attempts' in df.columns:
                df = df[df['pass_attempts'] >= 5]
        elif target_col == 'rushing_yards':
            # Filter out players with < 2 attempts
            if 'rush_attempts' in df.columns:
                df = df[df['rush_attempts'] >= 2]
        elif target_col == 'receiving_yards':
             # Filter out players with 0 targets
            if 'targets' in df.columns:
                df = df[df['targets'] >= 1]
                
        after_count = len(df)
        if before_count != after_count:
            logger.warning(f"Dropped {before_count - after_count} rows (NaNs or low volume)")
        
        # Train
        model = XGBoostModel(target_col=target_col)
        metrics = model.train(df, team_stats_df)
        
        logger.info(f"Metrics for {target_col}: {metrics}")
        
        if model_filename:
            model.save(model_filename)
            logger.info(f"Saved to {model_filename}")
            
    finally:
        db.close()

def main():
    # 1. Passing Yards (QB only)
    train_model_for_target(
        target_col='passing_yards', 
        position_filter=['QB'], 
        model_filename='passing_yards_model.joblib'
    )
    
    # 2. Rushing Yards (RB, QB)
    train_model_for_target(
        target_col='rushing_yards', 
        position_filter=['RB', 'QB'], 
        model_filename='rushing_yards_model.joblib'
    )
    
    # 3. Receiving Yards (WR, TE, RB)
    train_model_for_target(
        target_col='receiving_yards', 
        position_filter=['WR', 'TE', 'RB'], 
        model_filename='receiving_yards_model.joblib'
    )

if __name__ == "__main__":
    main()
