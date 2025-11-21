from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import Player
from app.schemas.schemas import PlayerBase

router = APIRouter()

@router.get("/players", response_model=List[PlayerBase])
async def get_players(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Simplified: In a real app, we'd join with Projections and PlayerSlate to get current stats
    # For now, returning basic player info mapped to the schema
    players = db.query(Player).offset(skip).limit(limit).all()
    
    # Mock mapping since our DB model doesn't exactly match the optimization schema yet
    # In production, we'd use a proper Pydantic 'from_orm' or a transformation layer
    result = []
    for p in players:
        result.append({
            "id": p.id,
            "name": f"{p.first_name} {p.last_name}",
            "position": p.position,
            "salary": 5000, # Placeholder
            "team": "UNK", # Placeholder
            "points": 15.0 # Placeholder
        })
    return result
