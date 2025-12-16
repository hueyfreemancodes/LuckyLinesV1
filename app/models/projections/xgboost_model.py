from .base_model import BaseProjectionModel
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import logging

logger = logging.getLogger(__name__)

class XGBoostModel(BaseProjectionModel):
    """
    XGBoost-based projection model for NFL.
    """
    
    def __init__(self, target_col: str = 'fantasy_points_ppr'):
        super().__init__(f"NFL_XGBoost_{target_col}")
        self.target_col = target_col
        self.model = None
        
    def prepare_features(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> tuple[pd.DataFrame, list]:
        """
        Feature engineering logic using the FeatureEngineering service.
        Returns (processed_df, feature_columns_list)
        """
        from app.services.feature_engineering import FeatureEngineering
        
        df = data.copy()
        
        # 1. Advanced Features (if team stats available)
        if team_stats is not None:
            df = FeatureEngineering.calculate_team_shares(df, team_stats)
            df = FeatureEngineering.calculate_red_zone_share(df, team_stats)
            df = FeatureEngineering.calculate_opportunity_share(df, team_stats)
            
        # 2. Time Series Features
        # 2. Time Series Features
        # EMAs
        ema_cols = ['fantasy_points_ppr', 'targets', 'rush_attempts', 'red_zone_share', 'opportunity_share']
        
        # Add target column to EMAs if not already present
        if self.target_col not in ema_cols and self.target_col in df.columns:
            ema_cols.append(self.target_col)
            
        df = FeatureEngineering.calculate_exponential_moving_averages(df, span=4, columns=ema_cols)
        
        # Lags
        lag_cols = ['fantasy_points_ppr', 'targets', 'rush_attempts']
        
        # Add target column to Lags if not already present
        if self.target_col not in lag_cols and self.target_col in df.columns:
            lag_cols.append(self.target_col)
            
        df = FeatureEngineering.calculate_lag_features(df, lags=[1], columns=lag_cols)
        
        # Streaks & Velocity
        df = FeatureEngineering.calculate_streak_coefficient(df)
        df = FeatureEngineering.calculate_velocity(df)
        df = FeatureEngineering.calculate_consecutive_streaks(df)
        
        # 3. Implied Totals (if available)
        df = FeatureEngineering.calculate_implied_totals(df)
        
        # 4. Weather Features
        # Requires: 'forecast_wind_speed', 'forecast_temp_low', 'forecast_humidity'
        # Also needs 'passing_yards_ema_4' for interaction, so calculate EMAs first (done above)
        # We need to ensure passing_yards EMA is calculated
        if 'passing_yards' in df.columns and 'passing_yards_ema_4' not in df.columns:
             df = FeatureEngineering.calculate_exponential_moving_averages(df, span=4, columns=['passing_yards'])

        df = FeatureEngineering.calculate_weather_features(df)
        
        # 5. Fantasy Context Features
        # Requires: 'vorp_last_season', 'ppg_last_season'
        df = FeatureEngineering.calculate_fantasy_context_features(df)
        
        # 6. Opponent Defense Features
        df = FeatureEngineering.calculate_opponent_defense_features(df)
        
        # 7. Game Script Features (Spread Interaction)
        df = FeatureEngineering.calculate_game_script_features(df)
        
        # 8. Expected Fantasy Points (xFP)
        df = FeatureEngineering.calculate_expected_fantasy_points(df)
        
        # 9. Define Feature List
        feature_cols = [
            'salary', 
            'fantasy_points_ppr_ema_4', 'targets_ema_4', 'rush_attempts_ema_4',
            'red_zone_share_ema_4', 'opportunity_share_ema_4',
            'fantasy_points_ppr_lag_1',
            'streak_coefficient',
            'implied_team_total', 'vegas_total', 'vegas_spread', # Added vegas_spread
            'fantasy_points_ppr_velocity',
            'fantasy_points_ppr_streak_over_15',
            # Position-Specific Weather Features
            'weather_wind_passing_penalty', 'weather_wind_rushing_boost', 
            'weather_temp_extreme', 'weather_high_humidity',
            # Fantasy Context Features (strong positive correlation)
            'vorp_last_season', 'player_ppg_trend', 'vorp_tier', 'ppg_tier', 
            'ppg_last_season', 'ppg_last_season_squared',
            # Opponent Defense Features
            'opp_def_ppg_allowed', 'opp_def_ypg_allowed', 
            'opp_def_sacks_per_game', 'opp_def_turnovers_per_game',
            'opp_def_strength_score',
            # Game Script Features
            'spread_passing_interaction', 'spread_rushing_interaction'
        ]
        
        # Add target-specific features
        if self.target_col != 'fantasy_points_ppr':
            feature_cols.append(f"{self.target_col}_ema_4")
            feature_cols.append(f"{self.target_col}_lag_1")
        
        # 10. Ensure all columns exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
                
        return df, feature_cols

    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        """
        Train XGBoost model.
        """
        target_col = self.target_col
        if target_col not in data.columns:
             raise ValueError(f"Training data missing target column: {target_col}")

        df, feature_cols = self.prepare_features(data, team_stats)
        
        X = df[feature_cols]
        y = df[target_col]
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Hyperparameters tuned to reduce overfitting
        self.model = xgb.XGBRegressor(
            objective='reg:absoluteerror', # Keep this from original
            n_estimators=100,        # Reduced from default 100 (was likely higher)
            max_depth=4,             # Reduced from 6 to limit tree complexity
            learning_rate=0.05,      # Reduced from 0.1 for more gradual learning
            min_child_weight=3,      # Increased from 1 to require more samples per leaf
            subsample=0.8,           # Use 80% of data for each tree (prevents overfitting)
            colsample_bytree=0.8,    # Use 80% of features for each tree
            reg_alpha=0.1,           # L1 regularization (Lasso)
            reg_lambda=1.0,          # L2 regularization (Ridge)
            gamma=0.1,               # Minimum loss reduction for split (pruning)
            random_state=42,
            n_jobs=-1,
            early_stopping_rounds=50
        )
        
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False
        )
        
        predictions = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, predictions)
        logger.info(f"XGBoost Model Trained. MAE: {mae:.2f}")
        
        feature_importance = dict(zip(feature_cols, self.model.feature_importances_))
        
        return {"mae": mae, "feature_importance": feature_importance}

    def predict(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.Series:
        """
        Generate projections.
        """
        if not self.model:
            raise ValueError("Model not trained or loaded.")
            
        df, feature_cols = self.prepare_features(data, team_stats)
        return self.model.predict(df[feature_cols])
