from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import Player
from app.schemas.schemas import PlayerBase

router = APIRouter()

@router.get("/players", response_model=List[PlayerBase])
async def get_players(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Fetch players from DB
    players = db.query(Player).offset(skip).limit(limit).all()
    
    result = []
    for p in players:
        # Map DB model to Pydantic schema
        # Note: salary and points are defaulting to 0/None as they reside in other tables (PlayerSlate, Projection)
        # In a real scenario, we would join with those tables or update the schema to be optional.
        result.append({
            "id": p.id,
            "name": f"{p.first_name} {p.last_name}",
            "position": p.position,
            "salary": 0,  # Defaulting as requested to remove mock data
            "team": "UNK", 
            "points": 0.0 
        })
    return result
