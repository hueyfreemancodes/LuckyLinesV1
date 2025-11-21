import sys
import os
import logging
from sqlalchemy import or_

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, Game, Team

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_game_ids():
    db = SessionLocal()
    try:
        # Fetch all Games
        games = db.query(Game).all()
        logger.info(f"Loaded {len(games)} games.")
        
        # Create a lookup map: (season, week, team_id) -> game_id
        # A game has two teams. So we map both home and away team to this game.
        game_lookup = {}
        for g in games:
            # Ensure season/week are populated
            if not g.season or not g.week:
                continue
                
            key_home = (g.season, g.week, g.home_team_id)
            key_away = (g.season, g.week, g.away_team_id)
            game_lookup[key_home] = g.id
            game_lookup[key_away] = g.id
            
        # Fetch all Teams to map abbreviation -> ID
        # CRITICAL: Prioritize full team names over "Team X" entries
        teams = db.query(Team).all()
        
        # First pass: only use teams with full names (not starting with "Team ")
        team_map = {}
        for t in teams:
            if not t.name.startswith("Team "):
                team_map[t.abbreviation] = t.id
        
        # Second pass: fill in gaps with "Team X" entries only if abbreviation not already mapped
        for t in teams:
            if t.name.startswith("Team ") and t.abbreviation not in team_map:
                team_map[t.abbreviation] = t.id
        
        # CRITICAL: Map standard abbreviations to the correct full team names
        # The full team names use non-standard abbreviations, so we need explicit mappings
        
        # Green Bay: "GRE" in DB, but "GB" in PlayerGameStats
        team_map['GB'] = team_map.get('GRE') or team_map.get('GB')
        team_map['GNB'] = team_map.get('GRE') or team_map.get('GB')
        
        # Tampa Bay: "TAM" in DB, but "TB" in PlayerGameStats
        team_map['TB'] = team_map.get('TAM') or team_map.get('TB')
        
        # New England: "NEW" in DB (shared with other teams), need to find correct one
        # ID=12 is New England Patriots
        team_map['NE'] = 12
        team_map['NEP'] = 12
        
        # New Orleans: "NEW" in DB (shared), need to find correct one
        # ID=23 is New Orleans Saints
        team_map['NO'] = 23
        team_map['NOR'] = 23
        
        # New York Giants: "NEW" in DB (shared)
        # ID=13 is New York Giants
        team_map['NYG'] = 13
        
        # New York Jets: "NEW" in DB (shared)
        # ID=8 is New York Jets
        team_map['NYJ'] = 8
        
        # Los Angeles Rams: "LOS" in DB
        # ID=26 is Los Angeles Rams
        team_map['LAR'] = 26
        team_map['LA'] = 26
        team_map['STL'] = 26  # Historical St. Louis Rams
        
        # Los Angeles Chargers: "LOS" in DB (duplicate!)
        # ID=43 is Los Angeles Chargers
        team_map['LAC'] = 43
        team_map['SD'] = 43  # Historical San Diego Chargers
        team_map['SDG'] = 43
        
        # Las Vegas Raiders: "LAS" in DB
        # ID=21 is Las Vegas Raiders
        team_map['LV'] = 21
        team_map['LVR'] = 21
        team_map['OAK'] = 21  # Historical Oakland Raiders
        team_map['RAI'] = 21
        
        # Miami Dolphins: "MIA" in DB
        # ID=42 is Miami Dolphins
        team_map['MIA'] = 42
        
        # Denver Broncos: "DEN" in DB
        # ID=44 is Denver Broncos
        team_map['DEN'] = 44
        
        # Washington: "WAS" in DB
        # ID=46 is Washington Commanders (most recent)
        team_map['WAS'] = 46
        team_map['WSH'] = 46
        
        # Jacksonville: "JAC" in DB
        # ID=20 is Jacksonville Jaguars
        team_map['JAX'] = 20
        team_map['JAC'] = 20
        
        # Tennessee Titans
        team_map['TEN'] = 17
        team_map['HST'] = 17  # Historical Houston Oilers
        
        # Indianapolis Colts
        team_map['IND'] = 16
        team_map['BLC'] = 16  # Baltimore Colts
        
        # Arizona Cardinals
        team_map['ARI'] = 19
        team_map['PHO'] = 19  # Phoenix Cardinals
        team_map['PHX'] = 19
        
        # Other teams (already correct)
        team_map['KC'] = 1
        team_map['KAN'] = 1
        team_map['SF'] = 2
        team_map['SFO'] = 2
        team_map['BAL'] = 3
        team_map['DET'] = 4
        team_map['BUF'] = 5
        team_map['PHI'] = 6
        team_map['HOU'] = 7
        team_map['CHI'] = 9
        team_map['PIT'] = 10
        team_map['CIN'] = 11
        team_map['MIN'] = 15
        team_map['SEA'] = 18
        team_map['CLE'] = 22
        team_map['ATL'] = 24
        team_map['DAL'] = 25
        team_map['CAR'] = 28




        
        # Iterate PlayerGameStats in chunks
        batch_size = 1000
        offset = 0
        total_updated = 0
        
        while True:
            stats = db.query(PlayerGameStats).filter(PlayerGameStats.game_id.is_(None)).limit(batch_size).all()
            if not stats:
                break
                
            updated_in_batch = 0
            for stat in stats:
                team_id = team_map.get(stat.team)
                if not team_id:
                    if updated_in_batch == 0 and total_updated == 0:
                        logger.warning(f"Team not found: {stat.team}")
                    continue
                    
                key = (stat.season, stat.week, team_id)
                game_id = game_lookup.get(key)
                
                if game_id:
                    stat.game_id = game_id
                    updated_in_batch += 1
                else:
                    if updated_in_batch == 0 and total_updated == 0:
                        logger.warning(f"Game not found for key: {key}")
                        # Log a few available keys for this season/week
                        sample_keys = [k for k in game_lookup.keys() if k[0] == stat.season and k[1] == stat.week]
                        logger.warning(f"Available keys for S{stat.season} W{stat.week}: {sample_keys[:5]}")
            
            db.commit()
            total_updated += updated_in_batch
            offset += batch_size
            logger.info(f"Processed batch. Total updated: {total_updated}")
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    backfill_game_ids()
