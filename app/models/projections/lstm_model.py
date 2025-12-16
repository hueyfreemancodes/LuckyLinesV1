from .base_model import BaseProjectionModel
import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import logging

logger = logging.getLogger(__name__)

class LSTMModel(BaseProjectionModel):
    """
    LSTM-based projection model for NFL.
    Handles sequence generation for time-series data.
    """
    
    def __init__(self):
        super().__init__("NFL_LSTM")
        self.scaler = StandardScaler()
        self.timesteps = 4 # Lookback window
        
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
        # EMAs
        ema_cols = ['fantasy_points_ppr', 'targets', 'rush_attempts', 'red_zone_share', 'opportunity_share']
        df = FeatureEngineering.calculate_exponential_moving_averages(df, span=4, columns=ema_cols)
        
        # Lags
        lag_cols = ['fantasy_points_ppr', 'targets', 'rush_attempts']
        df = FeatureEngineering.calculate_lag_features(df, lags=[1], columns=lag_cols)
        
        # Streaks & Velocity
        df = FeatureEngineering.calculate_streak_coefficient(df)
        df = FeatureEngineering.calculate_velocity(df)
        df = FeatureEngineering.calculate_consecutive_streaks(df)
        
        # 3. Implied Totals (if available)
        df = FeatureEngineering.calculate_implied_totals(df)
        
        # 5. Fantasy Context Features
        # Requires: 'vorp_last_season', 'ppg_last_season'
        df = FeatureEngineering.calculate_fantasy_context_features(df)
        
        # 6. Opponent Defense Features
        df = FeatureEngineering.calculate_opponent_defense_features(df)
        
        # 7. Expected Fantasy Points (xFP)
        df = FeatureEngineering.calculate_expected_fantasy_points(df)
        
        # 8. Define Feature List
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
            # Fantasy Context Features (strong positive correlation)
            'vorp_last_season', 'player_ppg_trend', 'vorp_tier', 'ppg_tier', 
            'ppg_last_season', 'ppg_last_season_squared',
            # Opponent Defense Features
            'opp_def_ppg_allowed', 'opp_def_ypg_allowed', 
            'opp_def_sacks_per_game', 'opp_def_turnovers_per_game',
            'opp_def_strength_score'
        ]
        
        # 6. Ensure all columns exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
                
        return df, feature_cols

    def create_sequences(self, df: pd.DataFrame, feature_cols: list, target_col: str):
        """
        Reshapes DataFrame into (Samples, Timesteps, Features)
        """
        # Sort by Player, Season, Week
        df = df.sort_values(['player_id', 'season', 'week'])
        
        sequences = []
        targets = []
        
        # Group by player
        # Group by player
        for _, group in df.groupby('player_id'):
            # Convert to numpy
            data = group[feature_cols].values
            target = group[target_col].values
            
            # Unified Zero-Padding Logic
            # We want to generate a prediction for EVERY row in the group.
            # To do this, we pad the beginning of the data with `timesteps` zeros.
            # Then we slide the window from 0 to len(group).
            
            padding_len = self.timesteps
            padded_data = np.pad(data, ((padding_len, 0), (0, 0)), 'constant')
            
            for i in range(len(group)):
                # Predict target[i] using sequence ending just before it
                # Sequence from padded_data[i : i+timesteps]
                # Example: i=0. seq = padded[0:timesteps] (all zeros). Target = target[0].
                sequences.append(padded_data[i : i + self.timesteps])
                targets.append(target[i])
                
        return np.array(sequences), np.array(targets)
                
            # Wait, the original logic was:
            # for i in range(self.timesteps, len(data)):
            #     sequences.append(data[i-self.timesteps:i])
            #     targets.append(target[i])
            # This predicts target[timesteps] using [0..timesteps-1].
            # It SKIPPED the first `timesteps` targets.
            
            # By padding, we are now including them.
            # This is a behavior change but a good one for "Week 1" support.
            
            # However, for INFERENCE (predict method), we usually want the sequence ending at the LAST row
            # to predict the FUTURE.
            # My loop above generates sequences to predict EXISTING targets.
            
            # `predict` method calls this:
            # X, _ = self.create_sequences(df, feature_cols, 'fantasy_points_ppr')
            # And then `model.predict(X)`.
            
            # If I change `create_sequences` to return N sequences for N rows...
            # `predict` will return N predictions.
            # In `ProjectionsService`, we map these back to the rows.
            
            # The `ProjectionsService` logic I just wrote:
            # valid_indices.extend(group.index[self.model.timesteps:])
            # This assumed the OLD logic (skipping first N).
            
            # If I change to padding, `valid_indices` should be `group.index[:]` (ALL rows).
            # This simplifies `ProjectionsService` too!
            
            # So, I will implement padding for ALL groups.
            
        return np.array(sequences), np.array(targets)

    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        """
        Train LSTM model.
        """
        target_col = 'fantasy_points_ppr'
        if target_col not in data.columns:
             raise ValueError(f"Training data missing target column: {target_col}")

        df, feature_cols = self.prepare_features(data, team_stats)
        
        # Fill NaNs explicitly before scaling
        df[feature_cols] = df[feature_cols].fillna(0)
        
        # Scale features
        # Note: In production, scaler should be fit on training data only and saved
        df[feature_cols] = self.scaler.fit_transform(df[feature_cols])
        
        # Create Sequences
        X, y = self.create_sequences(df, feature_cols, target_col)
        
        if len(X) == 0:
            logger.warning("Not enough data to create sequences for LSTM.")
            return {"mae": 0.0, "feature_importance": {}}
        
        # Split
        # Note: Random split breaks time series continuity for a single player, 
        # but since we have many players, it's acceptable for this MVP.
        # Ideally we split by player or time.
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Build Model
        self.model = Sequential()
        self.model.add(LSTM(128, input_shape=(self.timesteps, len(feature_cols)), return_sequences=False))
        self.model.add(Dropout(0.2))
        self.model.add(Dense(32, activation='relu'))
        self.model.add(Dense(1))
        
        self.model.compile(optimizer='adam', loss='mae')
        
        # Train
        self.model.fit(X_train, y_train, epochs=5, batch_size=64, validation_split=0.1, verbose=0)
        
        # Evaluate
        predictions = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, predictions)
        logger.info(f"LSTM Model Trained. MAE: {mae:.2f}")
        
        # Feature Importance (Not directly available in LSTM)
        feature_importance = {col: 0.0 for col in feature_cols}
        
        return {"mae": mae, "feature_importance": feature_importance}

    def predict(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.Series:
        """
        Generate projections.
        """
        if not self.model:
            raise ValueError("Model not trained or loaded.")
            
        df, feature_cols = self.prepare_features(data, team_stats)
        
        # Scale
        df[feature_cols] = self.scaler.transform(df[feature_cols])
        
        # For prediction, we need the *last* sequence for each player
        # This logic is complex for batch prediction of single upcoming games.
        # For MVP, we will assume the input `data` contains the necessary history 
        # or we just use the last row if it's a single row per player.
        
        # Simplified: Treat input as if it has history, but we only predict for the last row per player
        X, _ = self.create_sequences(df, feature_cols, 'fantasy_points_ppr') # Target dummy
        
        if len(X) == 0:
             return np.array([])
             
        return self.model.predict(X).flatten()

    def save(self, filename: str):
        """
        Save the trained LSTM model and scaler.
        Overrides base method to handle Keras model.
        """
        import os
        import joblib
        
        # Save Keras model
        keras_path = os.path.join(self.model_dir, filename.replace('.joblib', '.keras'))
        self.model.save(keras_path)
        logger.info(f"Saved LSTM model to {keras_path}")
        
        # Save Scaler
        scaler_path = os.path.join(self.model_dir, filename.replace('.joblib', '_scaler.joblib'))
        joblib.dump(self.scaler, scaler_path)
        logger.info(f"Saved Scaler to {scaler_path}")
        
        # Save Config
        import json
        config = {"timesteps": self.timesteps}
        config_path = os.path.join(self.model_dir, filename.replace('.joblib', '_config.json'))
        with open(config_path, 'w') as f:
            json.dump(config, f)
        logger.info(f"Saved Config to {config_path}")

    def load(self, filename: str):
        """
        Load the trained LSTM model and scaler.
        Overrides base method to handle Keras model.
        """
        import os
        import joblib
        import json
        from tensorflow.keras.models import load_model
        
        # Load Keras model
        keras_path = os.path.join(self.model_dir, filename.replace('.joblib', '.keras'))
        if os.path.exists(keras_path):
            self.model = load_model(keras_path)
            logger.info(f"Loaded LSTM model from {keras_path}")
        else:
            raise FileNotFoundError(f"LSTM model not found at {keras_path}")
            
        # Load Scaler
        scaler_path = os.path.join(self.model_dir, filename.replace('.joblib', '_scaler.joblib'))
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
            logger.info(f"Loaded Scaler from {scaler_path}")
        else:
            raise FileNotFoundError(f"Scaler not found at {scaler_path}")
            
        # Load Config
        config_path = os.path.join(self.model_dir, filename.replace('.joblib', '_config.json'))
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.timesteps = config.get("timesteps", 4)
            logger.info(f"Loaded Config from {config_path}: {config}")
