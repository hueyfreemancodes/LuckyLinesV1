import sys
import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, TeamGameOffenseStats, Game, PlayerSeasonStats, Player, Team, TeamGameDefenseStats
from app.models.projections.xgboost_model import XGBoostModel
from app.models.projections.lstm_model import LSTMModel
from app.models.projections.position_model import PositionBasedModel
from app.models.projections.stacked_model import StackedEnsembleModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_data():
    db = SessionLocal()
    try:
        logger.info("Fetching training data...")
        
        # Fetch PlayerGameStats with Position
        stats_query = db.query(PlayerGameStats, Player.position).join(Player, PlayerGameStats.player_id == Player.id)
        
        # Filter for valid data (e.g., points > 0 to avoid noise, or keep all?)
        # Keeping all for now, but maybe filter out players with 0 opportunity
        
        stats_with_position = stats_query.all()
        stats_data = [{
            **{c.name: getattr(stat, c.name) for c in PlayerGameStats.__table__.columns},
            'position': position
        } for stat, position in stats_with_position]
        
        # Fetch Team data for abbreviation mapping
        teams = db.query(Team).all()
        team_id_map = {t.id: t.abbreviation for t in teams}
        
        # Fetch Games for Weather and Opponent
        games = db.query(Game).all()
        game_map = {g.id: g for g in games}
        
        # Fetch Player Season Stats for VORP/PPG
        season_stats = db.query(PlayerSeasonStats).all()
        season_stats_map = {(s.player_id, s.season): s for s in season_stats}
        
        # Add derived data
        for row in stats_data:
            game_id = row.get('game_id')
            
            game = game_map.get(game_id)
            
            # 1. Weather
            row['forecast_wind_speed'] = game.forecast_wind_speed if game else 0
            row['forecast_temp_high'] = game.forecast_temp_high if game else 70
            row['forecast_temp_low'] = game.forecast_temp_low if game else 50
            row['forecast_humidity'] = game.forecast_humidity if game else 0
            
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
                player_team_abbrev = row.get('team')
                home_team_id = game.home_team_id
                away_team_id = game.away_team_id
                
                home_team_abbrev = team_id_map.get(home_team_id)
                away_team_abbrev = team_id_map.get(away_team_id)
                
                if player_team_abbrev == home_team_abbrev:
                    row['opponent'] = away_team_abbrev
                elif player_team_abbrev == away_team_abbrev:
                    row['opponent'] = home_team_abbrev
        
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
        defense_stats = db.query(TeamGameDefenseStats).all()
        defense_stats_df = pd.DataFrame([{
            'team_name': ds.team_name,
            'season': ds.season,
            'week': ds.week,
            'points_allowed': ds.points_allowed,
            'yards_allowed': ds.yards_allowed,
            'sacks': ds.sacks,
            'interceptions': ds.interceptions,
            'fumbles_recovered': ds.fumbles_recovered
        } for ds in defense_stats])
        
        return df, team_stats_df, defense_stats_df
        
    finally:
        db.close()

def main():
    df, team_stats_df, defense_stats_df = fetch_data()
    
    # Calculate opponent defense features globally first (since it's shared logic)
    # Actually, each model calls prepare_features which calls FeatureEngineering.
    # But FeatureEngineering.calculate_opponent_defense_features expects 'opponent' column.
    # We populated 'opponent' in fetch_data.
    # However, the `calculate_opponent_defense_features` method needs `defense_stats_df` passed to it?
    # Wait, looking at `feature_engineering.py`, the method signature is `calculate_opponent_defense_features(df)`.
    # It seems I implemented it as a placeholder in the class, but in `train_xgboost.py` I passed `defense_stats_df`.
    # Let's check `train_xgboost.py` again.
    # Ah, in `train_xgboost.py`, I imported `calculate_opponent_defense_features` from `app.services.opponent_defense_features`.
    # But in the models (`xgboost_model.py`, etc.), I'm calling `FeatureEngineering.calculate_opponent_defense_features(df)`.
    # This is a DISCREPANCY.
    
    # The models' `prepare_features` call `FeatureEngineering.calculate_opponent_defense_features(df)`.
    # But that method inside `FeatureEngineering` (which I edited) is just a placeholder that adds 0.0 columns!
    # The REAL calculation logic is in `app.services.opponent_defense_features`.
    
    # So, if I rely on `model.train()`, it calls `prepare_features`, which calls the PLACEHOLDER.
    # This means the models will see 0.0 for opponent defense features unless I pre-calculate them!
    
    # In `train_xgboost.py`, I manually called the real function BEFORE passing df to `model.train`.
    # But `model.train` calls `prepare_features` again.
    # If `prepare_features` overwrites the columns with 0.0, that's bad.
    # Let's check `FeatureEngineering.calculate_opponent_defense_features`.
    # It says: "if col not in df.columns: df[col] = 0.0".
    # So if I pre-calculate them, it WON'T overwrite them. Good.
    
    # So I MUST pre-calculate opponent defense features here in the script using the REAL service.
    from app.services.opponent_defense_features import calculate_opponent_defense_features
    df = calculate_opponent_defense_features(df, defense_stats_df)
    
    logger.info(f"Data ready. Shape: {df.shape}")
    
    # Split Data (Same split for all models)
    target_col = 'fantasy_points_ppr'
    X = df # Features are selected inside model.train, but we pass full df
    y = df[target_col]
    
    # We can't easily pass X_train/X_test to model.train because model.train expects full DF and does its own split.
    # This is a design flaw in `BaseProjectionModel.train` for comparison purposes.
    # However, `XGBoostModel.train` does `train_test_split(random_state=42)`.
    # If all models use `random_state=42`, they will split the same way!
    # Let's verify `LSTMModel` and others use 42.
    # XGBoost: 42. LSTM: 42. LightGBM: 42. CatBoost: 42. Stacked: 42.
    # So they are comparable.
    
    models = [
        XGBoostModel(),
        LSTMModel(),
        PositionBasedModel(XGBoostModel), # Pass class, not instance
        StackedEnsembleModel()
    ]
    
    results = []
    
    for model in models:
        logger.info(f"\nTraining {model.name}...")
        try:
            metrics = model.train(df, team_stats_df)
            results.append({
                "Model": model.name,
                "MAE": metrics['mae']
            })
            logger.info(f"Result: {model.name} - MAE: {metrics['mae']:.4f}")
        except Exception as e:
            logger.error(f"Failed to train {model.name}: {e}")
            results.append({
                "Model": model.name,
                "MAE": "Failed"
            })
            
    logger.info("\n=== FINAL COMPARISON ===")
    results_df = pd.DataFrame(results)
    print(results_df)
    
if __name__ == "__main__":
    main()
