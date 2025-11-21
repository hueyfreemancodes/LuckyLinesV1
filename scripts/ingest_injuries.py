import sys
import os
import logging
import pandas as pd
import nfl_data_py as nfl

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import Player, PlayerGameStats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ingest_injuries(season: int = 2025):
    """
    Ingest player availability status from nflverse weekly rosters.
    Updates the 'status' column in PlayerGameStats.
    """
    db = SessionLocal()
    
    logger.info(f"Fetching weekly rosters for {season}...")
    try:
        rosters = nfl.import_weekly_rosters([season])
    except Exception as e:
        logger.error(f"Failed to fetch roster data: {e}")
        return
    
    logger.info(f"Fetched {len(rosters)} roster records.")
    
    # Cache Players: (first_name, last_name) -> Player ID
    logger.info("Caching player map...")
    players = db.query(Player).all()
    name_map = {}
    lastname_team_map = {}  # Fallback for nickname mismatches
    
    for p in players:
        if p.first_name and p.last_name:
            key = (p.first_name.upper(), p.last_name.upper())
            name_map[key] = p.id
            
            # Also create a fallback map by (last_name, position)
            # This helps with nicknames like "C.J." vs "Coleridge"
            if p.position:
                fallback_key = (p.last_name.upper(), p.position.upper())
                if fallback_key not in lastname_team_map:
                    lastname_team_map[fallback_key] = []
                lastname_team_map[fallback_key].append(p.id)
    
    updated_count = 0
    created_count = 0
    skipped_count = 0
    
    # Batch-load all existing PlayerGameStats for this season
    logger.info(f"Loading existing PlayerGameStats for {season}...")
    existing_pgs = db.query(PlayerGameStats).filter(
        PlayerGameStats.season == season
    ).all()
    
    # Create a map: (player_id, week) -> PlayerGameStats
    pgs_map = {}
    for pgs in existing_pgs:
        key = (pgs.player_id, pgs.week)
        pgs_map[key] = pgs
    
    logger.info(f"Loaded {len(pgs_map)} existing records.")
    
    new_records = []
    
    for idx, row in rosters.iterrows():
        week = row['week']
        first_name = row.get('first_name')
        last_name = row.get('last_name')
        position = row.get('position')
        status = row.get('status', 'ACT')  # Default to ACT if missing
        
        if not last_name:
            skipped_count += 1
            continue
        
        # Try primary match by full name
        player_id = None
        if first_name:
            key_name = (first_name.upper(), last_name.upper())
            player_id = name_map.get(key_name)
        
        # Fallback: match by (last_name, position) if primary fails
        if not player_id and position:
            fallback_key = (last_name.upper(), position.upper())
            candidates = lastname_team_map.get(fallback_key, [])
            if len(candidates) == 1:
                # Only use fallback if there's exactly one match
                player_id = candidates[0]
        
        if not player_id:
            skipped_count += 1
            continue
        
        # Check if record exists
        key_pgs = (player_id, week)
        pgs = pgs_map.get(key_pgs)
        
        if pgs:
            # Update existing record
            if pgs.status != status:
                pgs.status = status
                updated_count += 1
        else:
            # Create placeholder record
            new_pgs = PlayerGameStats(
                player_id=player_id,
                season=season,
                week=week,
                status=status,
                team=row.get('team', '')
            )
            new_records.append(new_pgs)
            created_count += 1
    
    # Bulk insert new records
    if new_records:
        db.bulk_save_objects(new_records)
    
    db.commit()
    logger.info(f"Ingestion complete. Updated: {updated_count}, Created: {created_count}, Skipped: {skipped_count}")
    db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()
    
    ingest_injuries(args.season)
