import sys
import os
import logging
import pandas as pd
from typing import Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, Player, Team

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ingest_weekly_stats_from_nflverse(year: int = 2025, week: Optional[int] = None):
    """
    Ingest weekly player game stats from NFLverse.
    Populates PlayerGameStats table with passing, rushing, receiving stats.
    """
    try:
        import nfl_data_py as nfl
    except ImportError:
        logger.error("nfl-data-py not installed. Run: pip install nfl-data-py")
        return
    
    db = SessionLocal()
    try:
        logger.info(f"Fetching {year} weekly stats from NFLverse...")
        weekly_stats = nfl.import_weekly_data([year])
        
        if week:
            weekly_stats = weekly_stats[weekly_stats['week'] == week]
            logger.info(f"Filtered to Week {week}")
        
        logger.info(f"Found {len(weekly_stats)} player-week records")
        
        # Build player lookup by name
        players = db.query(Player).all()
        player_lookup = {}
        for p in players:
            # Try multiple name formats
            full_name = f"{p.first_name} {p.last_name}"
            player_lookup[full_name.lower()] = p.id
            # Also try just last name for matching
            player_lookup[p.last_name.lower()] = p.id
        
        # Build team lookup
        teams = db.query(Team).all()
        team_lookup = {t.abbreviation: t.id for t in teams}
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for _, row in weekly_stats.iterrows():
            player_name = row.get('player_display_name', row.get('player_name', ''))
            if not player_name:
                continue
            
            # Find player
            player_id = player_lookup.get(player_name.lower())
            if not player_id:
                # Try fuzzy match on last name only
                parts = player_name.split()
                if len(parts) >= 2:
                    last_name = parts[-1]
                    player_id = player_lookup.get(last_name.lower())
            
            if not player_id:
                skipped_count += 1
                continue
            
            season = int(row['season'])
            week_num = int(row['week'])
            
            # Check if record exists
            existing = db.query(PlayerGameStats).filter(
                PlayerGameStats.player_id == player_id,
                PlayerGameStats.season == season,
                PlayerGameStats.week == week_num
            ).first()
            
            # Extract stats
            stats_data = {
                'player_id': player_id,
                'season': season,
                'week': week_num,
                'opponent': row.get('opponent_team'),
                'fantasy_points_ppr': row.get('fantasy_points_ppr'),
                'passing_yards': row.get('passing_yards'),
                'passing_tds': row.get('passing_tds'),
                'interceptions': row.get('interceptions'),
                'rushing_yards': row.get('rushing_yards'),
                'rushing_tds': row.get('rushing_tds'),
                'receptions': row.get('receptions'),
                'targets': row.get('targets'),
                'receiving_yards': row.get('receiving_yards'),
                'receiving_tds': row.get('receiving_tds'),
                'rush_attempts': row.get('carries'),  # NFLverse uses 'carries', we use 'rush_attempts'
                'pass_attempts': row.get('attempts'),
                'pass_completions': row.get('completions'),
            }
            
            # Get team from recent_team or team column
            team_abbr = row.get('recent_team', row.get('team'))
            if team_abbr:
                stats_data['team'] = team_abbr
            
            if existing:
                # Update existing record
                for key, value in stats_data.items():
                    if value is not None and not pd.isna(value):
                        setattr(existing, key, value)
                updated_count += 1
            else:
                # Create new record
                new_stat = PlayerGameStats(**stats_data)
                db.add(new_stat)
                created_count += 1
            
            # Commit in batches
            if (created_count + updated_count) % 500 == 0:
                db.commit()
                logger.info(f"Progress: {created_count} created, {updated_count} updated")
        
        db.commit()
        
        logger.info(f"\n=== Weekly Stats Ingestion Complete ===")
        logger.info(f"Created: {created_count} records")
        logger.info(f"Updated: {updated_count} records")
        logger.info(f"Skipped: {skipped_count} (player not found)")
        
    except Exception as e:
        logger.error(f"Error ingesting weekly stats: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest NFL weekly player stats from NFLverse')
    parser.add_argument('--year', type=int, default=2025, help='Season year (default: 2025)')
    parser.add_argument('--week', type=int, help='Specific week (optional, defaults to all weeks)')
    
    args = parser.parse_args()
    
    logger.info(f"=== Ingesting {args.year} Weekly Stats ===")
    ingest_weekly_stats_from_nflverse(args.year, args.week)
    
    logger.info("\n✅ Ingestion complete!")

if __name__ == "__main__":
    main()
