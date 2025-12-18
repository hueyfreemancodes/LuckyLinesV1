from .base_model import BaseProjectionModel
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import logging

logger = logging.getLogger(__name__)

class NFLProjectionModel(BaseProjectionModel):
    """
    XGBoost-based projection model for NFL.
    """
    
    def __init__(self):
        super().__init__("NFL")
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
            
        ema = ['fantasy_points_ppr', 'targets', 'rush_attempts', 'red_zone_share', 'opportunity_share']
        df = FeatureEngineering.add_emas(df, span=4, cols=ema)
        
        lag = ['fantasy_points_ppr', 'targets', 'rush_attempts']
        df = FeatureEngineering.add_lags(df, lags=[1], cols=lag)
        
        df = FeatureEngineering.calc_streak(df)
        df = FeatureEngineering.calc_velocity(df)
        df = FeatureEngineering.add_streaks(df)
        
        df = FeatureEngineering.add_vegas_implied(df)
        
        # 4. Define Feature List
        feature_cols = [
            'salary', 
            'fantasy_points_ppr_ema_4', 'targets_ema_4', 'rush_attempts_ema_4',
            'red_zone_share_ema_4', 'opportunity_share_ema_4',
            'fantasy_points_ppr_lag_1',
            'target_share', 'rush_share', 'red_zone_share', 'opportunity_share',
            'streak_coefficient',
            'implied_team_total',
            'fantasy_points_ppr_velocity',
            'fantasy_points_ppr_streak_over_15',
            'red_zone_targets', 'red_zone_rush_attempts' # Raw RZ stats
        ]
        
        # 5. Ensure all columns exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
                
        return df, feature_cols

    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        """
        Train XGBoost model.
        """
        # Target is fantasy points (PPR by default for now)
        target_col = 'fantasy_points_ppr'
        if target_col not in data.columns:
             # Fallback if training data doesn't have pre-calculated points
             # In production, we'd calculate it from stats
             raise ValueError(f"Training data missing target column: {target_col}")

        df, feature_cols = self.prepare_features(data, team_stats)
        X = df[feature_cols]
        y = data[target_col]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        self.model = xgb.XGBRegressor(
            objective='reg:squarederror',
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5
        )
        
        self.model.fit(X_train, y_train)
        
        # Evaluate
        predictions = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, predictions)
        logger.info(f"NFL Model Trained. MAE: {mae:.2f}")
        
        # Feature Importance
        importance = self.model.feature_importances_
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
