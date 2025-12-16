import sys
import os
import logging
import pandas as pd
from sklearn.model_selection import train_test_split

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, TeamGameOffenseStats, Game, PlayerSeasonStats, Player, Team, VegasLine
from app.models.projections.xgboost_model import XGBoostModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    db = SessionLocal()
    try:
        logger.info("Fetching training data...")
        
        # Fetch PlayerGameStats with Player join to get position
        stats_query = db.query(
            PlayerGameStats,
            Player.position
        ).join(
            Player, PlayerGameStats.player_id == Player.id
        ).filter(
            PlayerGameStats.fantasy_points_ppr.isnot(None)
        )
        
        stats_with_position = stats_query.all()
        stats_data = [{\
            **{c.name: getattr(stat, c.name) for c in PlayerGameStats.__table__.columns},
            'position': position
        } for stat, position in stats_with_position]
        
        # Fetch Teams for mapping IDs to Abbreviations
        teams = db.query(Team).all()
        team_id_map = {t.id: t.abbreviation for t in teams}
        
        # Abbreviation Normalization Map
        # Maps various abbreviations to the standard used in TeamGameDefenseStats
        ABBR_MAP = {
            'JAC': 'JAX', 'STL': 'LAR', 'SL': 'LAR', 'SD': 'LAC', 'SDG': 'LAC',
            'OAK': 'LV', 'LVR': 'LV', 'LAS': 'LV', 'TAM': 'TB', 'TBB': 'TB',
            'KAN': 'KC', 'KNC': 'KC', 'NWE': 'NE', 'NOR': 'NO', 'SFO': 'SF',
            'GNB': 'GB', 'GRE': 'GB', 'WSH': 'WAS', 'HST': 'HOU', 'CLV': 'CLE',
            'BLT': 'BAL', 'ARZ': 'ARI', 'LA': 'LAR' # Assuming LA -> LAR (Rams)
        }
        
        def normalize_abbr(abbr):
            if not abbr: return None
            return ABBR_MAP.get(abbr, abbr)
            
        # Fetch Games
        games = db.query(Game).all()
        game_map = {g.id: g for g in games}
        
        # Fetch Player Season Stats for VORP/PPG
        season_stats = db.query(PlayerSeasonStats).all()
        season_stats_map = {(s.player_id, s.season): s for s in season_stats}
        
        # Fetch Vegas Lines
        vegas_lines = db.query(VegasLine).all()
        vegas_map = {vl.game_id: vl for vl in vegas_lines}
        
        # Add derived data
        for row in stats_data:
            game_id = row.get('game_id')
            player_team_id = row.get('team_id') # Note: PlayerGameStats might not have team_id, check model
            
            # If team_id is missing in stats, we might need to get it from Player or Team string
            # But let's assume we can get it. If not, we rely on 'team' string if it matches abbreviation
            
            game = game_map.get(game_id)
            
            # 1. Weather
            row['forecast_wind_speed'] = game.forecast_wind_speed if game else 0
            row['forecast_temp_high'] = game.forecast_temp_high if game else 70
            row['forecast_temp_low'] = game.forecast_temp_low if game else 50
            row['forecast_temp_low'] = game.forecast_temp_low if game else 50
            row['forecast_humidity'] = game.forecast_humidity if game else 0
            
            # 1b. Vegas Lines
            v_line = vegas_map.get(game_id)
            row['vegas_total'] = v_line.total_points if v_line else 0.0
            row['vegas_spread'] = v_line.spread if v_line else 0.0
            
            # 2. Previous Season Stats
            prev_season_key = (row['player_id'], row['season'] - 1)
            prev_stats = season_stats_map.get(prev_season_key)
            row['vorp_last_season'] = prev_stats.vorp if prev_stats and prev_stats.vorp is not None else 0.0
            
            if prev_stats and prev_stats.fantasy_points_ppr and prev_stats.games_played and prev_stats.games_played > 0:
                row['ppg_last_season'] = prev_stats.fantasy_points_ppr / prev_stats.games_played
            else:
                row['ppg_last_season'] = 0.0
                
            # 3. Opponent Derivation
            row['opponent'] = None
            if game:
                # We need to know which team the player is on to find the opponent
                # PlayerGameStats has 'team' (abbreviation) usually
                player_team_abbrev = row.get('team')
                
                home_team_id = game.home_team_id
                away_team_id = game.away_team_id
                
                home_team_abbrev = team_id_map.get(home_team_id)
                away_team_abbrev = team_id_map.get(away_team_id)
                
                if player_team_abbrev == home_team_abbrev:
                    row['opponent'] = normalize_abbr(away_team_abbrev)
                elif player_team_abbrev == away_team_abbrev:
                    row['opponent'] = normalize_abbr(home_team_abbrev)
                else:
                    # Fallback: try to match by ID if available
                    # But 'team' in PlayerGameStats is likely the abbreviation
                    pass
        
        df = pd.DataFrame(stats_data)
        
        # Fetch TeamGameOffenseStats
        team_stats = db.query(TeamGameOffenseStats).all()
        team_stats_df = pd.DataFrame([{
            'team_name': ts.team_name,
            'season': ts.season,
            'week': ts.week,
            'total_yards': ts.total_yards,
            'pass_attempts': ts.pass_attempts,
            'rush_attempts': ts.rush_attempts
        } for ts in team_stats])
        
        # Fetch TeamGameDefenseStats
        from app.models.models import TeamGameDefenseStats
        defense_stats = db.query(TeamGameDefenseStats).all()
        defense_stats_df = pd.DataFrame([{
            'team': normalize_abbr(ds.team_name), # Normalize defense team names too
            'season': ds.season,
            'week': ds.week,
            'points_allowed': ds.points_allowed,
            'yards_allowed': ds.yards_allowed,
            'sacks': ds.sacks,
            'interceptions': ds.interceptions,
            'fumbles_recovered': ds.fumbles_recovered
        } for ds in defense_stats])
        
        # Filter for rows with valid opponent data
        # We only want to train on data where we have the context features
        logger.info(f"Total rows before filtering: {len(df)}")
        df = df[df['opponent'].notna()]
        logger.info(f"Rows with valid opponent: {len(df)}")
        
        # Calculate opponent defense features
        from app.services.opponent_defense_features import calculate_opponent_defense_features
        df = calculate_opponent_defense_features(df, defense_stats_df)
        
        # Calculate Implied Totals
        from app.services.feature_engineering import FeatureEngineering
        df = FeatureEngineering.calculate_implied_totals(df)
        
        # DEBUG: Check if opponent defense features are populated
        logger.info("\n=== OPPONENT DEFENSE DATA CHECK ===")
        defense_cols = ['opp_def_ppg_allowed', 'opp_def_ypg_allowed', 'opp_def_sacks_per_game', 'opp_def_strength_score']
        logger.info(df[defense_cols].describe())
        logger.info("\nSample rows:")
        logger.info(df[defense_cols].head())
        
        # Check for non-zero values
        non_zero = (df['opp_def_ppg_allowed'] > 0).sum()
        logger.info(f"Rows with non-zero defensive stats: {non_zero}/{len(df)} ({100*non_zero/len(df):.1f}%)")
        
        logger.info(f"Rows with non-zero defensive stats: {non_zero}/{len(df)} ({100*non_zero/len(df):.1f}%)")
        
        # Ensure target column is numeric and drop NaNs
        target_col = 'fantasy_points_ppr'
        df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
        before_count = len(df)
        df = df.dropna(subset=[target_col])
        
        # Filter out low-value records (noise)
        # Players with < 1.0 fantasy points likely didn't play a meaningful role
        df = df[df[target_col] >= 1.0]
        after_count = len(df)
        
        if before_count != after_count:
            logger.warning(f"Dropped {before_count - after_count} rows (NaNs or < 1.0 pts)")

        logger.info(f"Training XGBoost Model on {len(df)} rows...")
        
        # Split data for overfitting analysis
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
        
        # Train model
        model = XGBoostModel()
        metrics = model.train(train_df, team_stats_df)
        
        # Calculate overfitting metrics
        train_predictions = model.predict(train_df, team_stats_df)
        test_predictions = model.predict(test_df, team_stats_df)
        
        train_mae = (train_df['fantasy_points_ppr'] - train_predictions).abs().mean()
        test_mae = (test_df['fantasy_points_ppr'] - test_predictions).abs().mean()
        overfitting_gap = test_mae - train_mae
        overfitting_ratio = test_mae / train_mae if train_mae > 0 else 1.0
        
        logger.info(f"Training Complete. Metrics: {metrics}")
        logger.info(f"\n=== OVERFITTING ANALYSIS ===")
        logger.info(f"Train MAE: {train_mae:.4f}")
        logger.info(f"Test MAE: {test_mae:.4f}")
        logger.info(f"Overfitting Gap: {overfitting_gap:.4f} ({100*overfitting_gap/test_mae:.1f}% of test MAE)")
        logger.info(f"Overfitting Ratio: {overfitting_ratio:.3f} (ideal: ~1.0, concerning: >1.15)")
        
        if overfitting_ratio > 1.15:
            logger.warning("⚠️  Model is overfitting! Consider:")
            logger.warning("   - Reducing max_depth")
            logger.warning("   - Increasing min_child_weight")
            logger.warning("   - Adding regularization (reg_alpha, reg_lambda)")
        elif overfitting_ratio < 1.05:
            logger.info("✅ Model generalization is good!")
        
        # Save Model
        logger.info("Saving model...")
        model.save("nfl_xgboost_model.joblib")
        logger.info("Model saved to nfl_xgboost_model.joblib")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
