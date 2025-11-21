from typing import Dict, Any
import pandas as pd
import numpy as np
import logging
import os
from .base_model import BaseProjectionModel

logger = logging.getLogger(__name__)

class PositionBasedModel(BaseProjectionModel):
    """
    Wrapper class that trains separate models for each position (QB, RB, WR, TE).
    """
    
    def __init__(self, base_model_class, **kwargs):
        """
        Args:
            base_model_class: The class of the model to use (e.g., LSTMModel, XGBoostModel).
            **kwargs: Arguments to pass to the base model constructor.
        """
        # We don't call super().__init__ with a fixed name because we want to reflect the base model
        self.base_model_class = base_model_class
        self.model_kwargs = kwargs
        self.models: Dict[str, BaseProjectionModel] = {}
        self.positions = ['QB', 'RB', 'WR', 'TE']
        
        # Initialize sub-models
        for pos in self.positions:
            self.models[pos] = base_model_class(**kwargs)
            
        # Set name for logging
        self.name = f"PositionBased_{self.models['QB'].name}"
        self.model_dir = "models" # Default
        
    def train(self, data: pd.DataFrame, team_stats: pd.DataFrame = None):
        """
        Splits data by position and trains each sub-model.
        """
        results = {}
        total_mae = 0
        count = 0
        
        # Ensure position column exists (it should be in 'player_position' or 'position')
        pos_col = 'position'
        if pos_col not in data.columns:
            # Try to infer or fail
            if 'player_position' in data.columns:
                pos_col = 'player_position'
            else:
                # If we joined with Player table, it might be there. 
                # If not, we can't do position-based modeling.
                raise ValueError("Data must contain 'position' column for PositionBasedModel.")
        
        for pos in self.positions:
            logger.info(f"Training {pos} model...")
            pos_data = data[data[pos_col] == pos].copy()
            
            if len(pos_data) < 50: # Minimum threshold
                logger.warning(f"Not enough data for {pos} ({len(pos_data)} rows). Skipping.")
                continue
                
            metrics = self.models[pos].train(pos_data, team_stats)
            results[pos] = metrics
            
            # Weighted MAE contribution
            total_mae += metrics['mae'] * len(pos_data)
            count += len(pos_data)
            
        avg_mae = total_mae / count if count > 0 else 0.0
        logger.info(f"Position-Based Training Complete. Weighted MAE: {avg_mae:.2f}")
        
        return {"mae": avg_mae, "details": results}

    def predict(self, data: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.Series:
        """
        Splits data by position, predicts, and recombines.
        """
        pos_col = 'position'
        if pos_col not in data.columns:
             if 'player_position' in data.columns:
                pos_col = 'player_position'
             else:
                raise ValueError("Data must contain 'position' column.")
        
        # Initialize empty series with same index
        predictions = pd.Series(index=data.index, dtype=float)
        predictions[:] = 0.0 # Default
        
        for pos in self.positions:
            # Identify rows for this position
            mask = data[pos_col] == pos
            if not mask.any():
                continue
                
            pos_data = data[mask].copy()
            
            # Predict
            try:
                pos_preds = self.models[pos].predict(pos_data, team_stats)
                
                # Assign back using index
                # Note: predict returns numpy array or Series. 
                # If numpy, we need to ensure alignment.
                if isinstance(pos_preds, (np.ndarray, list)):
                    predictions.loc[mask] = pos_preds
                else:
                    predictions.loc[mask] = pos_preds.values
            except Exception as e:
                logger.error(f"Error predicting for {pos}: {e}")
                
        return predictions

    def save(self, filename: str):
        """
        Saves each sub-model with a suffix.
        """
        for pos, model in self.models.items():
            # Inject suffix before extension
            if '.' in filename:
                parts = filename.rsplit('.', 1)
                pos_filename = f"{parts[0]}_{pos}.{parts[1]}"
            else:
                pos_filename = f"{filename}_{pos}"
                
            model.save(pos_filename)
            
    def load(self, filename: str):
        """
        Loads each sub-model.
        """
        for pos, model in self.models.items():
            if '.' in filename:
                parts = filename.rsplit('.', 1)
                pos_filename = f"{parts[0]}_{pos}.{parts[1]}"
            else:
                pos_filename = f"{filename}_{pos}"
            
            try:
                model.load(pos_filename)
            except FileNotFoundError:
                logger.warning(f"Could not load model for {pos} at {pos_filename}")
