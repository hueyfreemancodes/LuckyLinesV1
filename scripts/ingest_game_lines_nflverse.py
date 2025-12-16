import logging
import sys
import os
import nfl_data_py as nfl
import pandas as pd
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import Game, VegasLine, Team

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Team Abbreviation Mapping (NFLverse -> DB)
TEAM_MAPPING = {
    'ARZ': 'ARI',
    'BLT': 'BAL',
    'CLV': 'CLE',
    'HST': 'HOU',
    'LA': 'LAR',
    'LAC': 'LAC',
    'JAC': 'JAX',
    'SD': 'LAC',
    'SDG': 'LAC',
    'SL': 'LAR',
    'STL': 'LAR',
    'OAK': 'LV',
    'LV': 'LV',
    'LVR': 'LV',
    'SF': 'SF',
    'SFO': 'SF',
    'TB': 'TB',
    'TAM': 'TB',
    'WAS': 'WAS',
    'WSH': 'WAS',
    'NE': 'NE',
    'NWE': 'NE',
    'KC': 'KC',
    'KAN': 'KC',
    'GB': 'GB',
    'GNB': 'GB',
    'NO': 'NO',
    'NOR': 'NO'
}

def normalize_abbr(abbr):
    return TEAM_MAPPING.get(abbr, abbr)

def ingest_game_lines(start_year=2012, end_year=2025):
    db = SessionLocal()
    try:
        years = list(range(start_year, end_year + 1))
        logger.info(f"Fetching schedule data for {years}...")
        
        schedule = nfl.import_schedules(years)
        logger.info(f"Fetched {len(schedule)} games.")
        
        # Cache Teams
        teams = db.query(Team).all()
        team_map = {t.abbreviation: t.id for t in teams}
        
        processed_count = 0
        updated_count = 0
        
        for _, row in schedule.iterrows():
            season = row['season']
            week = row['week']
            home_abbr = normalize_abbr(row['home_team'])
            away_abbr = normalize_abbr(row['away_team'])
            
            # Skip if no lines
            if pd.isna(row['spread_line']) or pd.isna(row['total_line']):
                continue
                
            # Find Game in DB
            # We match on Season, Week, and Home Team
            home_team_id = team_map.get(home_abbr)
            if not home_team_id:
                # logger.warning(f"Could not find team ID for {home_abbr}")
                continue
                
            game = db.query(Game).filter(
                Game.season == season,
                Game.week == week,
                Game.home_team_id == home_team_id
            ).first()
            
            if not game:
                # Try matching by away team if home team match failed (unlikely but possible)
                # logger.warning(f"Game not found: {season} W{week} {home_abbr} vs {away_abbr}")
                continue
            
            # Calculate Implied Totals
            # spread_line: Positive means Home Favorite (Home Score > Away Score)
            # Home Implied = (Total + Spread) / 2
            # Away Implied = (Total - Spread) / 2
            
            spread = float(row['spread_line'])
            total = float(row['total_line'])
            
            home_implied = (total + spread) / 2
            away_implied = (total - spread) / 2
            
            # Check for existing VegasLine
            vegas_line = db.query(VegasLine).filter(VegasLine.game_id == game.id).first()
            
            if vegas_line:
                # Update
                vegas_line.spread = spread
                vegas_line.total_points = total
                vegas_line.home_implied_total = home_implied
                vegas_line.away_implied_total = away_implied
                vegas_line.source = 'nflverse'
                vegas_line.updated_at = datetime.now()
                updated_count += 1
            else:
                # Create
                vegas_line = VegasLine(
                    game_id=game.id,
                    source='nflverse',
                    spread=spread,
                    total_points=total,
                    home_implied_total=home_implied,
                    away_implied_total=away_implied
                )
                db.add(vegas_line)
                processed_count += 1
                
            if (processed_count + updated_count) % 1000 == 0:
                db.commit()
                logger.info(f"Processed {processed_count + updated_count} lines...")
                
        db.commit()
        logger.info(f"Ingestion Complete. Created {processed_count}, Updated {updated_count} lines.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    ingest_game_lines()
