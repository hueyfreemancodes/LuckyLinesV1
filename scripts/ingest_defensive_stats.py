import sys
import os
import requests
import logging
from datetime import datetime

sys.path.append(os.getcwd())
from app.core.database import SessionLocal, engine
from app.models.models import TeamGameDefenseStats, Team

# Support local execution by overriding DB URL if not set
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/dfs_db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = "9f52850ed5494c11ae371312e036e97b"
BASE_URL = "https://api.sportsdata.io/v3/nfl/stats/json/FantasyDefenseByGameByTeam"

# Team abbreviations mapping
TEAM_ABBREVS = [
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS'
]

def fetch_defensive_stats(season, week, team):
    """
    Fetch defensive stats for a specific team, season, and week.
    """
    url = f"{BASE_URL}/{season}/{week}/{team}?key={API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {team} S{season} W{week}: {e}")
        return None

def ingest_defensive_stats(start_season=2022, end_season=2024, start_week=1, end_week=18):
    """
    Ingest defensive stats for all teams across specified seasons and weeks.
    """
    db = SessionLocal()
    
    try:
        # Get team mapping
        teams = db.query(Team).all()
        team_map = {t.abbreviation: t.id for t in teams}
        
        total_ingested = 0
        total_skipped = 0
        
        for season in range(start_season, end_season + 1):
            logger.info(f"\n=== Processing Season {season} ===")
            
            for week in range(start_week, end_week + 1):
                logger.info(f"Week {week}...")
                
                for team_abbrev in TEAM_ABBREVS:
                    import time
                    time.sleep(0.2) # Rate limiting
                    # Check if already exists
                    existing = db.query(TeamGameDefenseStats).filter(
                        TeamGameDefenseStats.season == season,
                        TeamGameDefenseStats.week == week,
                        TeamGameDefenseStats.team_name == team_abbrev
                    ).first()
                    
                    if existing:
                        total_skipped += 1
                        continue
                    
                    # Fetch from API
                    data = fetch_defensive_stats(season, week, team_abbrev)
                    
                    if not data:
                        continue
                    
                    # Parse response (it's a single object, not a list)
                    team_id = team_map.get(team_abbrev)
                    
                    # Create record
                    defense_stat = TeamGameDefenseStats(
                        team_id=team_id,
                        team_name=team_abbrev,
                        season=season,
                        week=week,
                        opponent=data.get('Opponent'),
                        points_allowed=data.get('PointsAllowed', 0),
                        yards_allowed=data.get('OffensiveYardsAllowed', 0.0),
                        sacks=data.get('Sacks', 0.0),
                        interceptions=data.get('Interceptions', 0),
                        fumbles_recovered=data.get('FumblesRecovered', 0)
                    )
                    
                    db.add(defense_stat)
                    total_ingested += 1
                    
                    # Commit every 32 teams (one week)
                    if total_ingested % 32 == 0:
                        db.commit()
                        logger.info(f"  Committed {total_ingested} records")
        
        # Final commit
        db.commit()
        
        logger.info(f"\n=== INGESTION COMPLETE ===")
        logger.info(f"Total ingested: {total_ingested}")
        logger.info(f"Total skipped (already exists): {total_skipped}")
        
    except Exception as e:
        logger.error(f"Error during ingestion: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Ingest last 2 seasons (focus on recent data)
    ingest_defensive_stats(start_season=2024, end_season=2025, start_week=1, end_week=18)
