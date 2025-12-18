from .base_model import BaseProjectionModel
from .xgboost_model import XGBoostModel
from .lightgbm_model import LightGBMModel
from .catboost_model import CatBoostModel
from .lstm_model import LSTMModel
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
import logging

logger = logging.getLogger(__name__)

class StackedEnsembleModel(BaseProjectionModel):
    """
    Stacked Ensemble Model.
    Combines predictions from XGBoost, LightGBM, CatBoost, and LSTM using a Linear Regression meta-learner.
    """
    
    def __init__(self):
        super().__init__("NFL_Stacked_Ensemble")
        self.base_models = {
            "xgboost": XGBoostModel(),
            "lightgbm": LightGBMModel(),
            "catboost": CatBoostModel(),
            "lstm": LSTMModel()
        }
        self.meta_learner = LinearRegression()
        
    def prepare_features(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> tuple[pd.DataFrame, list]:
        """
        Pass-through to base models. 
        The ensemble doesn't have its own features per se, but we need a common interface.
        We'll use the LSTM's feature set as the 'superset' if needed, but really each model handles its own.
        """
        # Just return data as is, base models will process it.
        return data, [] 

    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        """
        Train the Stacked Ensemble.
        1. Split data into Train and Holdout (Meta-Train).
        2. Train Base Models on Train.
        3. Predict on Holdout to get Meta-Features.
        4. Train Meta-Learner on Meta-Features -> Target.
        5. (Optional) Retrain Base Models on Full Data.
        """
        target_col = 'fantasy_points_ppr'
        if target_col not in data.columns:
             raise ValueError(f"Training data missing target column: {target_col}")

        # 1. Split Data
        # We use a 50/50 split for Base/Meta training to avoid overfitting the meta-learner
        # In production with more data, we'd use K-Fold Stacking.
        X_base, X_meta, y_base, y_meta = train_test_split(data, data[target_col], test_size=0.5, random_state=42)
        
        logger.info(f"Training Base Models on {len(X_base)} records...")
        
        # 2. Train Base Models
        for name, model in self.base_models.items():
            logger.info(f"Training {name}...")
            try:
                model.train(X_base, team_stats)
            except Exception as e:
                logger.error(f"Failed to train {name}: {e}")
                
        # 3. Generate Meta-Features
        logger.info("Generating Meta-Features...")
        meta_features = pd.DataFrame(index=X_meta.index)
        
        for name, model in self.base_models.items():
            try:
                preds = model.predict(X_meta, team_stats)
                meta_features[f'pred_{name}'] = preds
            except Exception as e:
                logger.error(f"Failed to predict {name}: {e}")
                meta_features[f'pred_{name}'] = 0.0
                
        # 4. Train Meta-Learner
        logger.info("Training Meta-Learner...")
        # Fill NaNs if any model failed
        meta_features = meta_features.fillna(0)
        
        self.meta_learner.fit(meta_features, y_meta)
        
        logger.info(f"Meta-Learner Coefficients: {dict(zip(meta_features.columns, self.meta_learner.coef_))}")
        logger.info(f"Meta-Learner Intercept: {self.meta_learner.intercept_}")
        
        # Evaluate on Meta Set (Self-Consistency check)
        final_preds = self.meta_learner.predict(meta_features)
        from sklearn.metrics import mean_absolute_error
        mae = mean_absolute_error(y_meta, final_preds)
        
        logger.info(f"Stacked Model Meta-MAE: {mae:.2f}")
        
        # 5. Return weights
        return {"mae": mae, "weights": dict(zip(meta_features.columns, self.meta_learner.coef_))}

    def predict(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.Series:
        """
        Generate projections using the ensemble.
        """
        meta_features = pd.DataFrame(index=data.index)
        
        for name, model in self.base_models.items():
            try:
                preds = model.predict(data, team_stats)
                meta_features[f'pred_{name}'] = preds
            except Exception as e:
                logger.error(f"Failed to predict {name}: {e}")
                meta_features[f'pred_{name}'] = 0.0
                
        meta_features = meta_features.fillna(0)
        
        return self.meta_learner.predict(meta_features)
