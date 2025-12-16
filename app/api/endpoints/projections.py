from fastapi import APIRouter, HTTPException, Depends
from typing import List, Any, Dict
from app.services.projections import ProjectionsService

router = APIRouter()

@router.get("/nfl/{season}/{week}", response_model=List[Dict[str, Any]])
async def get_nfl_projections(season: int, week: int):
    """
    Get NFL projections for a specific week using the trained LSTM model.
    """
    service = ProjectionsService()
    projections = service.generate_projections(season, week)
    
    if not projections:
        raise HTTPException(status_code=404, detail="No projections found or model error.")
        
    return projections
