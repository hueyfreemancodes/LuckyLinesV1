from abc import ABC, abstractmethod
import pandas as pd
import joblib
import os
from typing import List, Dict, Any

class BaseProjectionModel(ABC):
    """
    Abstract base class for sport-specific projection models.
    """
    
    def __init__(self, sport: str, model_dir: str = "models"):
        self.sport = sport
        self.name = sport # Use sport as name by default
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        self.model = None
        
    @abstractmethod
    def train(self, data: pd.DataFrame):
        """
        Train the model on historical data.
        """
        pass
        
    @abstractmethod
    def predict(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate projections for new data.
        """
        pass
        
    def save(self, filename: str):
        """Save the trained model to disk."""
        path = os.path.join(self.model_dir, filename)
        joblib.dump(self.model, path)
        
    def load(self, filename: str):
        """Load a trained model from disk."""
        path = os.path.join(self.model_dir, filename)
        if os.path.exists(path):
            self.model = joblib.load(path)
        else:
            raise FileNotFoundError(f"Model not found at {path}")
