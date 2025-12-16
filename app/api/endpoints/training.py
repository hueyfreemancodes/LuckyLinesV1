from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import HistoricalPerformance, Player
from app.models.projections.nfl_model import NFLProjectionModel
import pandas as pd
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

def train_model_task(sport: str, db: Session):
    """
    Background task to train the model.
    """
    try:
        logger.info(f"Starting training for {sport}...")
        
        # 1. Fetch Data
        # Join PlayerGameStats with Player to get details
        from app.models.models import PlayerGameStats
        
        query = db.query(PlayerGameStats, Player).join(Player, PlayerGameStats.player_id == Player.id)
        results = query.all()
        
        if not results:
            logger.warning("No historical data found for training.")
            return

        data = []
        for stats, player in results:
            # Basic feature extraction
            data.append({
                "fantasy_points_ppr": stats.fantasy_points_ppr,
                "salary": 5000, # Placeholder as salary is not in PlayerGameStats yet (needs separate join)
                "team_id": player.team_id,
                "is_home": 1 if stats.is_home else 0,
                
                # Detailed Stats
                "pass_attempts": stats.pass_attempts,
                "pass_completions": stats.pass_completions,
                "passing_yards": stats.passing_yards,
                "passing_tds": stats.passing_tds,
                "interceptions": stats.interceptions,
                "rush_attempts": stats.rush_attempts,
                "rushing_yards": stats.rushing_yards,
                "rushing_tds": stats.rushing_tds,
                "targets": stats.targets,
                "receptions": stats.receptions,
                "receiving_yards": stats.receiving_yards,
                "receiving_tds": stats.receiving_tds
            })
            
        df = pd.DataFrame(data)
        
        # 2. Train Model
        if sport == "NFL":
            model = NFLProjectionModel()
            metrics = model.train(df)
            model.save("nfl_model.joblib")
            logger.info(f"Training complete. Metrics: {metrics}")
            
    except Exception as e:
        logger.error(f"Training failed: {e}")

@router.post("/training/train")
async def trigger_training(
    sport: str, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger ML model training in the background.
    """
    if sport != "NFL":
        raise HTTPException(status_code=400, detail="Only NFL supported for MVP")
        
    background_tasks.add_task(train_model_task, sport, db)
    return {"message": f"Training started for {sport}"}
