from .base_model import BaseProjectionModel
from .xgboost_model import XGBoostModel
from .lightgbm_model import LightGBMModel
from .catboost_model import CatBoostModel
from .lstm_model import LSTMModel
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
import logging

logger = logging.getLogger(__name__)

class StackedEnsembleModel(BaseProjectionModel):
    """
    Combines XGBoost, LightGBM, CatBoost, and LSTM predictions via Linear Regression meta-learner.
    """
    
    def __init__(self):
        super().__init__("NFL_Stacked_Ensemble")
        self.learners = {
            "xgboost": XGBoostModel(),
            "lightgbm": LightGBMModel(),
            "catboost": CatBoostModel(),
            "lstm": LSTMModel()
        }
        self.meta = LinearRegression()
        
    def prepare_features(self, df: pd.DataFrame, team_stats: pd.DataFrame = None) -> tuple[pd.DataFrame, list]:
        """Pass-through (base learners handle their own FE)."""
        return df, []

    def _get_meta_features(self, df, team_stats):
        meta = pd.DataFrame(index=df.index)
        for name, model in self.learners.items():
            try:
                meta[f'pred_{name}'] = model.predict(df, team_stats)
            except Exception as e:
                logger.error(f"Failed prediction for {name}: {e}")
                meta[f'pred_{name}'] = 0.0
        return meta.fillna(0)

    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        target = 'fantasy_points_ppr'
        if target not in data:
             raise ValueError(f"Missing target: {target}")

        # Split: Base Training (50%) vs Meta Training (50%)
        # In prod, use K-Fold cross-validation for stacking to use 100% of data efficiently.
        train_split, holdout_split, _, y_holdout = train_test_split(
            data, data[target], test_size=0.5, random_state=42
        )
        
        logger.info(f"Training base learners on {len(train_split)} rows...")
        for name, model in self.learners.items():
            try:
                model.train(train_split, team_stats)
            except Exception as e:
                logger.error(f"Failed training {name}: {e}")
                
        logger.info("Generating meta-features...")
        meta_X = self._get_meta_features(holdout_split, team_stats)
        
        logger.info("Training meta-learner...")
        self.meta.fit(meta_X, y_holdout)
        
        # Log weights
        weights = dict(zip(meta_X.columns, self.meta.coef_))
        logger.info(f"Meta-Learner Weights: {weights}")
        
        # Eval
        final_preds = self.meta.predict(meta_X)
        from sklearn.metrics import mean_absolute_error
        mae = mean_absolute_error(y_holdout, final_preds)
        
        return {"mae": mae, "weights": weights}

    def predict(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.Series:
        meta_X = self._get_meta_features(data, team_stats)
        return self.meta.predict(meta_X)
