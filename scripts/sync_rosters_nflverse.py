import sys
import os
import logging
from typing import Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import Player, Team, DepthChart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sync_rosters_from_nflverse(year: int = 2024):
    """
    Sync NFL rosters from NFLverse data.
    Updates player team assignments for the specified year.
    """
    try:
        import nfl_data_py as nfl
    except ImportError:
        logger.error("nfl-data-py not installed. Run: pip install nfl-data-py")
        return
    
    db = SessionLocal()
    try:
        logger.info(f"Fetching {year} weekly rosters from NFLverse...")
        weekly_rosters = nfl.import_weekly_rosters([year])
        
        # Use Week 12 (current regular season week)
        # TODO: Make this dynamic or accept as parameter
        target_week = 12
        logger.info(f"Using Week {target_week} roster data")
        
        # Filter for target week and active players
        current_rosters = weekly_rosters[weekly_rosters['week'] == target_week]
        active_players = current_rosters[current_rosters['status'] == 'ACT']
        logger.info(f"Found {len(active_players)} active players in Week {target_week}")
        
        # Team abbreviation mapping (NFLverse → Our DB)
        team_map = _build_team_map(db)
        
        updated_count = 0
        created_count = 0
        not_found_count = 0
        
        for _, row in active_players.iterrows():
            player_name = row['player_name']
            team_abbr = row['team']
            position = row['position']
            gsis_id = row.get('gsis_id')
            
            # Find team in our DB
            team_id = team_map.get(team_abbr)
            if not team_id:
                logger.warning(f"Team not found in DB: {team_abbr}")
                continue
            
            # Find player in our DB
            player = _find_player_by_name(db, player_name)
            
            if player:
                # Update existing player
                if player.team_id != team_id:
                    old_team = db.query(Team).filter(Team.id == player.team_id).first()
                    new_team = db.query(Team).filter(Team.id == team_id).first()
                    logger.info(f"Updating {player_name}: {old_team.abbreviation if old_team else '?'} → {new_team.abbreviation if new_team else '?'}")
                    player.team_id = team_id
                    updated_count += 1
                
                # Update external IDs if available
                if gsis_id and player.external_ids:
                    if isinstance(player.external_ids, dict):
                        player.external_ids['gsis'] = gsis_id
                    else:
                        player.external_ids = {'gsis': gsis_id}
                elif gsis_id:
                    player.external_ids = {'gsis': gsis_id}
                    
            else:
                # Create new player
                logger.info(f"Creating new player: {player_name} ({team_abbr}, {position})")
                parts = player_name.split()
                first_name = parts[0] if len(parts) > 0 else player_name
                last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
                
                new_player = Player(
                    sport_id=1,  # NFL
                    team_id=team_id,
                    first_name=first_name,
                    last_name=last_name,
                    position=position,
                    external_ids={'gsis': gsis_id} if gsis_id else {}
                )
                db.add(new_player)
                created_count += 1
        
        db.commit()
        
        logger.info(f"\n=== Roster Sync Complete ===")
        logger.info(f"Updated: {updated_count} players")
        logger.info(f"Created: {created_count} new players")
        logger.info(f"Not Found: {not_found_count} players")
        
    except Exception as e:
        logger.error(f"Error syncing rosters: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

def sync_depth_charts_from_nflverse(year: int = 2024, week: Optional[int] = None):
    """
    Sync NFL depth charts from NFLverse data.
    Stores weekly depth chart data for all teams.
    """
    try:
        import nfl_data_py as nfl
    except ImportError:
        logger.error("nfl-data-py not installed. Run: pip install nfl-data-py")
        return
    
    db = SessionLocal()
    try:
        logger.info(f"Fetching {year} depth charts from NFLverse...")
        depth_charts = nfl.import_depth_charts([year])
        
        if week:
            depth_charts = depth_charts[depth_charts['week'] == week]
            logger.info(f"Filtered to Week {week}")
        
        logger.info(f"Found {len(depth_charts)} depth chart entries")
        
        # Team abbreviation mapping
        team_map = _build_team_map(db)
        
        # Clear existing depth charts for this season/week
        if week:
            db.query(DepthChart).filter(
                DepthChart.season == year,
                DepthChart.week == week
            ).delete()
        else:
            db.query(DepthChart).filter(DepthChart.season == year).delete()
        
        added_count = 0
        
        for _, row in depth_charts.iterrows():
            team_abbr = row.get('club_code', row.get('team'))
            season = row['season']
            week_num = row['week']
            position = row.get('position', row.get('pos'))
            depth_position = row.get('depth_position', row.get('depth_team', ''))
            player_name = row.get('full_name', row.get('player_name', ''))
            jersey_number = row.get('jersey_number')
            elias_id = row.get('elias_id')
            gsis_id = row.get('gsis_id')
            
            # Find team
            team_id = team_map.get(team_abbr)
            if not team_id:
                continue
            
            # Find player (optional - may not be in our DB yet)
            player = _find_player_by_name(db, player_name)
            player_id = player.id if player else None
            
            # Create depth chart entry
            depth_entry = DepthChart(
                season=season,
                week=week_num,
                team_id=team_id,
                position=position,
                depth_position=depth_position,
                player_id=player_id,
                player_name=player_name,
                jersey_number=str(jersey_number) if jersey_number else None,
                elias_id=elias_id,
                gsis_id=gsis_id
            )
            db.add(depth_entry)
            added_count += 1
        
        db.commit()
        
        logger.info(f"\n=== Depth Chart Sync Complete ===")
        logger.info(f"Added: {added_count} depth chart entries")
        
    except Exception as e:
        logger.error(f"Error syncing depth charts: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

def _build_team_map(db) -> dict:
    """Build mapping of team abbreviations to team IDs."""
    teams = db.query(Team).filter(Team.sport_id == 1).all()
    
    # Create map with both full names and abbreviations
    team_map = {}
    for team in teams:
        team_map[team.abbreviation] = team.id
        # Also map common variations
        if team.abbreviation == 'KC':
            team_map['KAN'] = team.id
        elif team.abbreviation == 'SF':
            team_map['SFO'] = team.id
        elif team.abbreviation == 'GB':
            team_map['GNB'] = team.id
            team_map['GRE'] = team.id
        elif team.abbreviation == 'TB':
            team_map['TAM'] = team.id
            team_map['TBB'] = team.id
        elif team.abbreviation == 'NE':
            team_map['NWE'] = team.id
        elif team.abbreviation == 'NO':
            team_map['NOR'] = team.id
        elif team.abbreviation == 'LAR':
            team_map['LA'] = team.id
            team_map['STL'] = team.id
        elif team.abbreviation == 'LAC':
            team_map['SD'] = team.id
            team_map['SDG'] = team.id
        elif team.abbreviation == 'LV':
            team_map['OAK'] = team.id
            team_map['LVR'] = team.id
            team_map['LAS'] = team.id
        elif team.abbreviation == 'WAS':
            team_map['WSH'] = team.id
        elif team.abbreviation == 'JAX':
            team_map['JAC'] = team.id
    
    return team_map

def _find_player_by_name(db, full_name: str) -> Optional[Player]:
    """Find player by full name with fuzzy matching."""
    parts = full_name.split()
    if len(parts) < 2:
        return None
    
    first_name = parts[0]
    last_name = ' '.join(parts[1:])
    
    # Try exact match
    player = db.query(Player).filter(
        Player.first_name.ilike(first_name),
        Player.last_name.ilike(last_name)
    ).first()
    
    if player:
        return player
    
    # Try last name only (for cases like "J. Allen" → "Josh Allen")
    player = db.query(Player).filter(
        Player.last_name.ilike(last_name)
    ).first()
    
    return player

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync NFL rosters and depth charts from NFLverse')
    parser.add_argument('--year', type=int, default=2025, help='Season year (default: 2025)')
    parser.add_argument('--week', type=int, help='Specific week for depth charts (optional)')
    parser.add_argument('--rosters-only', action='store_true', help='Only sync rosters, skip depth charts')
    parser.add_argument('--depth-charts-only', action='store_true', help='Only sync depth charts, skip rosters')
    
    args = parser.parse_args()
    
    if not args.depth_charts_only:
        logger.info("=== PHASE 1: Syncing Rosters ===")
        sync_rosters_from_nflverse(args.year)
    
    if not args.rosters_only:
        logger.info("\n=== PHASE 2: Syncing Depth Charts ===")
        sync_depth_charts_from_nflverse(args.year, args.week)
    
    logger.info("\n✅ Sync complete!")

if __name__ == "__main__":
    main()
