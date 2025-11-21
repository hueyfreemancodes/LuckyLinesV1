import pandas as pd
import re
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Player, PlayerGameStats, Team
from app.core.database import DATABASE_URL

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_week(date_str, season):
    """Map date to NFL week."""
    try:
        d = pd.to_datetime(date_str)
        # Approx start dates (Thursday of Week 1)
        starts = {
            2013: datetime(2013, 9, 5), 2014: datetime(2014, 9, 4),
            2015: datetime(2015, 9, 10), 2016: datetime(2016, 9, 8),
            2017: datetime(2017, 9, 7), 2018: datetime(2018, 9, 6),
            2019: datetime(2019, 9, 5), 2020: datetime(2020, 9, 10),
            2021: datetime(2021, 9, 9), 2022: datetime(2022, 9, 8),
            2023: datetime(2023, 9, 7), 2024: datetime(2024, 9, 5)
        }
        start = starts.get(season)
        if not start: return 1
        
        # Days since start
        delta = d - start
        week = (delta.days // 7) + 1
        return max(1, min(18, week)) # Clamp to 1-18
    except:
        return 1

def process_pbp_file(file_path):
    db = SessionLocal()
    try:
        logger.info(f"Processing {file_path}...")
        
        # Regex for names: "P.Mahomes"
        name_pattern = re.compile(r'([A-Z]\.[A-Za-z]+)')
        
        chunk_size = 100000
        total_processed = 0
        
        # Pre-load players to minimize DB lookups
        # Cache: { "F.LASTNAME": player_id }
        logger.info("Caching players...")
        players = db.query(Player).all()
        player_cache = {}
        for p in players:
            # Store as "F.LASTNAME"
            key = f"{p.first_name[0]}.{p.last_name}".upper()
            player_cache[key] = p.id
            
        logger.info(f"Cached {len(player_cache)} players.")

        debug_matches = 0

        for chunk in pd.read_csv(file_path, chunksize=chunk_size, na_values=['\\N']):
            # Normalize columns
            chunk.columns = chunk.columns.str.replace(' ', '').str.replace(':', '').str.replace('Unnamed', 'Unk')
            
            # Filter Red Zone (YardLine >= 80 means inside opponent 20)
            # Ensure numeric
            chunk['YardLine'] = pd.to_numeric(chunk['YardLine'], errors='coerce')
            rz_plays = chunk[chunk['YardLine'] >= 80].copy()
            
            if rz_plays.empty:
                continue
                
            # Vectorized parsing is hard with regex extraction of multiple groups
            # Let's iterate the filtered RZ plays (much smaller subset)
            
            agg_stats = {} # (Season, Week, PlayerID) -> Stats
            
            for _, row in rz_plays.iterrows():
                desc = str(row.get('Description', ''))
                if not desc: continue
                
                # Find all "F.Lastname" or "F.LASTNAME"
                matches = name_pattern.findall(desc)
                if not matches: continue
                
                try:
                    season = int(float(row.get('SeasonYear', 2023)))
                except (ValueError, TypeError):
                    season = 2023 # Fallback
                date_str = row.get('GameDate')
                week = get_week(date_str, season)
                
                is_pass = 'pass' in desc.lower()
                is_rush = 'tackle' in desc.lower() or 'run' in desc.lower() or 'rush' in desc.lower()
                is_td = 'touchdown' in desc.lower()
                
                # Helper to update stats
                def update_stat(p_name, type_):
                    nonlocal debug_matches
                    # Lookup using UPPERCASE
                    p_id = player_cache.get(p_name.upper())
                    
                    if not p_id: 
                        return # Skip unknown players
                    
                    if debug_matches < 5:
                        logger.info(f"MATCH: {p_name} -> ID {p_id} (Season {season}, Week {week})")
                        debug_matches += 1
                    
                    k = (season, week, p_id)
                    if k not in agg_stats:
                        agg_stats[k] = {
                            'rz_pass':0, 'rz_rush':0, 'rz_target':0, 
                            'rz_pass_td':0, 'rz_rush_td':0, 'rz_rec_td':0
                        }
                    
                    if type_ == 'pass':
                        agg_stats[k]['rz_pass'] += 1
                        if is_td: agg_stats[k]['rz_pass_td'] += 1
                    elif type_ == 'target':
                        agg_stats[k]['rz_target'] += 1
                        if is_td: agg_stats[k]['rz_rec_td'] += 1
                    elif type_ == 'rush':
                        agg_stats[k]['rz_rush'] += 1
                        if is_td: agg_stats[k]['rz_rush_td'] += 1

                if is_pass:
                    update_stat(matches[0], 'pass')
                    if 'to ' in desc.lower() and len(matches) > 1:
                        update_stat(matches[1], 'target')
                elif is_rush:
                    update_stat(matches[0], 'rush')

            # Bulk Update DB for this chunk
            # We need to fetch existing stats and update them
            # Or just update in place.
            # Doing this row-by-row for thousands of players is still slow but better than millions of plays.
            
            updates = 0
            for (season, week, p_id), stats in agg_stats.items():
                pgs = db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == p_id,
                    PlayerGameStats.season == season,
                    PlayerGameStats.week == week
                ).first()
                
                if pgs:
                    pgs.red_zone_pass_attempts = stats['rz_pass']
                    pgs.red_zone_rush_attempts = stats['rz_rush']
                    pgs.red_zone_targets = stats['rz_target']
                    pgs.red_zone_passing_tds = stats['rz_pass_td']
                    pgs.red_zone_rushing_tds = stats['rz_rush_td']
                    pgs.red_zone_receiving_tds = stats['rz_rec_td']
                    updates += 1
            
            db.commit()
            total_processed += len(chunk)
            logger.info(f"Processed {total_processed} rows. Updated {updates} player stats.")
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_pbp.py <path_to_csv>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    process_pbp_file(file_path)
