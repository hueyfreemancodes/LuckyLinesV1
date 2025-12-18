from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.ingestion.csv_ingestion import CSVIngestion

router = APIRouter()

@router.post("/ingest/salaries")
async def ingest_salaries(
    file: UploadFile = File(...),
    platform: str = Form(...), # DraftKings, FanDuel
    season: int = Form(...),
    week: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Upload a Salary CSV (DK/FD) to populate PlayerSlate table.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
        
    try:
        content = await file.read()
        ingestion = CSVIngestion(db)
        count = ingestion.process_salary_csv(content, platform, season, week)
        return {"message": f"Successfully processed {count} salary records for {platform} Week {week}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest/csv")
async def ingest_csv(
    file: UploadFile = File(...),
    sport: str = Query(...),
    source: str = Query(...),
    type: str = Query("projection"), # 'projection' or 'history'
    dataset_type: str = Query("player_offense"), # 'player_offense', 'player_defense', etc.
    db: Session = Depends(get_db)
):
    """
    Upload a CSV file containing player projections or historical data.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
        
    try:
        content = await file.read()
        ingestion = CSVIngestion(db)
        
        if type == "history":
            if dataset_type == "player_offense":
                count = ingestion.process_player_stats_offense(content)
                return {"message": f"Successfully processed {count} player offensive records"}
            elif dataset_type == "player_defense":
                count = ingestion.process_player_stats_defense(content)
                return {"message": f"Successfully processed {count} player defensive records"}
            elif dataset_type == "team_offense":
                count = ingestion.process_team_stats_offense(content)
                return {"message": f"Successfully processed {count} team offensive records"}
            elif dataset_type == "team_defense":
                count = ingestion.process_team_stats_defense(content)
                return {"message": f"Successfully processed {count} team defensive records"}
            elif dataset_type == "play_by_play":
                count = ingestion.process_play_by_play(content)
                return {"message": f"Successfully processed {count} play-by-play records"}
            else:
                return {"message": f"Dataset type {dataset_type} not yet implemented"}
        else:
            count = ingestion.process_csv(content, sport, source)
            return {"message": f"Successfully processed {count} projections from {file.filename}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
