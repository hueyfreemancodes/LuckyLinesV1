from .base_model import BaseProjectionModel
import pandas as pd
import catboost as cb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import logging

logger = logging.getLogger(__name__)

class CatBoostModel(BaseProjectionModel):
    """
    CatBoost-based projection model for NFL.
    """
    
    def __init__(self):
        super().__init__("NFL_CatBoost")
        self.features = [
            'salary',
            'is_home'
        ]
        
    def prepare_features(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> tuple[pd.DataFrame, list]:
        """
        Feature engineering logic using the FeatureEngineering service.
        Returns (processed_df, feature_columns_list)
        """
        from app.services.feature_engineering import FeatureEngineering
        
        df = data.copy()
        
        # 1. Advanced Features (if team stats available)
        if team_stats is not None:
            df = FeatureEngineering.add_team_shares(df, team_stats)
            df = FeatureEngineering.add_rz_share(df, team_stats)
            df = FeatureEngineering.add_opp_share(df, team_stats)
            
        # Time Series
        cols_ema = ['fantasy_points_ppr', 'targets', 'rush_attempts', 'red_zone_share', 'opportunity_share']
        df = FeatureEngineering.add_emas(df, span=4, cols=cols_ema)
        
        cols_lag = ['fantasy_points_ppr', 'targets', 'rush_attempts']
        df = FeatureEngineering.add_lags(df, lags=[1], cols=cols_lag)
        
        df = FeatureEngineering.calc_streak(df)
        df = FeatureEngineering.calc_velocity(df)
        df = FeatureEngineering.add_streaks(df)
        
        df = FeatureEngineering.add_vegas_implied(df)
        df = FeatureEngineering.add_fantasy_context(df)
        df = FeatureEngineering.add_def_features(df)
        
        # 6. Define Feature List
        feature_cols = [
            'salary', 
            'fantasy_points_ppr_ema_4', 'targets_ema_4', 'rush_attempts_ema_4',
            'red_zone_share_ema_4', 'opportunity_share_ema_4',
            'fantasy_points_ppr_lag_1',
            'streak_coefficient',
            'implied_team_total',
            'fantasy_points_ppr_velocity',
            'fantasy_points_ppr_streak_over_15',
            # Position-Specific Weather Features
            'weather_wind_passing_penalty', 'weather_wind_rushing_boost', 
            'weather_temp_extreme', 'weather_high_humidity',
            # Fantasy Context Features
            'vorp_last_season', 'player_ppg_trend', 'vorp_tier', 'ppg_tier', 
            'ppg_last_season', 'ppg_last_season_squared',
            # Opponent Defense Features
            'opp_def_ppg_allowed', 'opp_def_ypg_allowed', 
            'opp_def_sacks_per_game', 'opp_def_turnovers_per_game',
            'opp_def_strength_score'
        ]
        
        # 5. Ensure all columns exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
                
        return df, feature_cols

    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        """
        Train CatBoost model.
        """
        target_col = 'fantasy_points_ppr'
        if target_col not in data.columns:
             raise ValueError(f"Training data missing target column: {target_col}")

        df, feature_cols = self.prepare_features(data, team_stats)
        X = df[feature_cols]
        y = data[target_col]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        self.model = cb.CatBoostRegressor(
            iterations=100,
            learning_rate=0.1,
            depth=5,
            loss_function='MAE',
            verbose=False
        )
        
        self.model.fit(X_train, y_train)
        
        # Evaluate
        predictions = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, predictions)
        logger.info(f"CatBoost Model Trained. MAE: {mae:.2f}")
        
        # Feature Importance
        importance = self.model.get_feature_importance()
        feature_importance = dict(zip(feature_cols, importance.tolist()))
        
        return {"mae": mae, "feature_importance": feature_importance}

    def predict(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.Series:
        """
        Generate projections.
        """
        if not self.model:
            raise ValueError("Model not trained or loaded.")
            
        df, feature_cols = self.prepare_features(data, team_stats)
        X = df[feature_cols]
        return self.model.predict(X)
