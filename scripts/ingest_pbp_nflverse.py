import sys
import os
import logging
import pandas as pd
import nfl_data_py as nfl
from sqlalchemy import func

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import Player, Game, Team, PlayerGameStats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapping from NFLverse abbreviations to DB abbreviations
TEAM_MAPPING = {
    'JAX': 'JAC',
    'LAC': 'LOS',
    'LAR': 'LOS',
    'LV': 'LAS',
    'NE': 'NEW',
    'NO': 'NEW',
    'NYJ': 'NEW',
    'NYG': 'NEW',
    'GB': 'GRE',
    'TB': 'TAM',
    'SF': 'SF', 
    'KC': 'KAN',
    'WSH': 'WAS'
}

def get_db_team_abbr(nfl_abbr):
    return TEAM_MAPPING.get(nfl_abbr, nfl_abbr)

def ingest_pbp_data(year: int = 2025):
    """
    Ingest PBP data from NFLverse for the specified year.
    Extracts Red Zone stats and updates PlayerGameStats.
    """
    db = SessionLocal()
    
    logger.info(f"Fetching PBP data for {year} from NFLverse...")
    try:
        # Use direct URL to bypass NameError bug in nfl-data-py v0.3.1
        # The library tries to catch an undefined 'Error' when 404 happens
        pbp_url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet"
        pbp = pd.read_parquet(pbp_url)
    except Exception as e:
        logger.error(f"Failed to fetch PBP data for {year}. Ensure the data exists and URL is correct: {e}")
        return

    logger.info(f"Fetched {len(pbp)} rows. Processing plays...")
    
    # Filter for valid play types (pass, run)
    # We process ALL plays now, not just Red Zone
    plays = pbp[
        (pbp['play_type'].isin(['pass', 'run'])) &
        (pbp['season_type'] == 'REG')
    ]
    
    logger.info(f"Found {len(plays)} valid plays.")
    
    # Cache Players: GSIS ID -> Player ID
    # And (Name, Team) -> Player ID as fallback
    logger.info("Caching player map...")
    players = db.query(Player).all()
    gsis_map = {}
    name_team_map = {} # (FIRST LAST, TEAM) -> ID
    f_last_map = {} # (F.Lastname, TEAM) -> ID
    
    for p in players:
        # Map GSIS ID
        if p.external_ids and isinstance(p.external_ids, dict):
            gsis = p.external_ids.get('gsis')
            if gsis:
                gsis_map[gsis] = p.id
        
        if p.team:
            # Full Name Map
            key = (f"{p.first_name} {p.last_name}".upper(), p.team.abbreviation)
            name_team_map[key] = p.id
            
            # F.Lastname Map
            if p.first_name and p.last_name:
                f_last = f"{p.first_name[0]}.{p.last_name}".upper()
                key_f = (f_last, p.team.abbreviation)
                f_last_map[key_f] = p.id

    # Cache Games: (Season, Week, Home, Away) -> Game ID
    logger.info("Caching game map...")
    games = db.query(Game).filter(Game.season == year).all()
    game_map = {} # (Week, HomeAbbr, AwayAbbr) -> Game
    
    for g in games:
        if g.home_team and g.away_team:
            key = (g.week, g.home_team.abbreviation, g.away_team.abbreviation)
            game_map[key] = g

    # Cache Teams: Abbr -> ID
    teams = db.query(Team).all()
    team_id_map = {t.abbreviation: t.id for t in teams}

    # Aggregate Stats
    # Key: (GameID, PlayerID) -> Stats Dict
    player_game_stats = {}
    # Key: (GameID, TeamAbbr) -> Stats Dict
    team_game_stats = {}
    
    # Helper to get/create stats entry
    def get_stats_entry(game_id, player_id, team_abbr):
        k = (game_id, player_id)
        if k not in player_game_stats:
            player_game_stats[k] = {
                'pass_attempts': 0, 'pass_completions': 0, 'passing_yards': 0, 'passing_tds': 0, 'interceptions': 0,
                'rush_attempts': 0, 'rushing_yards': 0, 'rushing_tds': 0,
                'targets': 0, 'receptions': 0, 'receiving_yards': 0, 'receiving_tds': 0,
                'red_zone_pass_attempts': 0, 'red_zone_rush_attempts': 0, 'red_zone_targets': 0,
                'red_zone_passing_tds': 0, 'red_zone_rushing_tds': 0, 'red_zone_receiving_tds': 0,
                'team_abbr': team_abbr
            }
        return player_game_stats[k]

    def get_team_stats_entry(game_id, team_abbr):
        k = (game_id, team_abbr)
        if k not in team_game_stats:
            team_game_stats[k] = {
                'pass_attempts': 0, 'rush_attempts': 0, 'total_yards': 0, 'turnovers': 0
            }
        return team_game_stats[k]

    # Helper to resolve player
    def resolve_player(nfl_id, nfl_name, nfl_team):
        # Try GSIS ID
        if nfl_id in gsis_map:
            return gsis_map[nfl_id]
        
        # Try Name + Team
        db_team = get_db_team_abbr(nfl_team)
        if nfl_name and db_team:
            # NFLverse 'passer' is usually 'J.Allen'
            key = (nfl_name.upper(), db_team)
            if key in f_last_map:
                return f_last_map[key]
                
            # Try exact match just in case
            if key in name_team_map:
                return name_team_map[key]
            
            # Log failure for debugging (sample)
            if "DANIELS" in nfl_name.upper():
                logger.warning(f"Failed to resolve {nfl_name} ({nfl_team}) -> Key: {key}. Available keys sample: {list(f_last_map.keys())[:5]}")
                
        return None

    processed_plays = 0
    
    for idx, play in plays.iterrows():
        week = play['week']
        home_team = get_db_team_abbr(play['home_team'])
        away_team = get_db_team_abbr(play['away_team'])
        
        # Find Game
        game = game_map.get((week, home_team, away_team))
        if not game:
            continue
            
        game_id = game.id
        is_red_zone = (play['yardline_100'] <= 20)
        
        # Process Passing
        if play['play_type'] == 'pass':
            passer_id = play.get('passer_player_id')
            passer_name = play.get('passer')
            receiver_id = play.get('receiver_player_id')
            receiver_name = play.get('receiver')
            posteam = play.get('posteam')
            db_posteam = get_db_team_abbr(posteam)
            
            # Team Stats
            ts = get_team_stats_entry(game_id, db_posteam)
            ts['pass_attempts'] += 1
            ts['total_yards'] += play.get('yards_gained', 0)
            if play.get('interception', 0) == 1:
                ts['turnovers'] += 1
            
            # Passer
            if passer_id or passer_name:
                pid = resolve_player(passer_id, passer_name, posteam)
                if pid:
                    s = get_stats_entry(game_id, pid, db_posteam)
                    if play.get('pass_attempt') == 1:
                        s['pass_attempts'] += 1
                        if is_red_zone: s['red_zone_pass_attempts'] += 1
                    
                    if play.get('complete_pass') == 1:
                        s['pass_completions'] += 1
                        
                    s['passing_yards'] += play.get('yards_gained', 0) # Includes sack yards? Usually passing_yards column is better but yards_gained works for now.
                    # Actually nfl-data-py has 'passing_yards' column which is None/NaN on incompletions
                    p_yards = play.get('passing_yards')
                    if p_yards is not None and not pd.isna(p_yards):
                         s['passing_yards'] = s['passing_yards'] - play.get('yards_gained', 0) + p_yards
                    
                    if play.get('touchdown') == 1 and play.get('td_team') == posteam:
                         s['passing_tds'] += 1
                         if is_red_zone: s['red_zone_passing_tds'] += 1
                    
                    if play.get('interception') == 1:
                        s['interceptions'] += 1
            
            # Receiver
            if receiver_id or receiver_name:
                pid = resolve_player(receiver_id, receiver_name, posteam)
                if pid:
                    s = get_stats_entry(game_id, pid, db_posteam)
                    s['targets'] += 1 
                    if is_red_zone: s['red_zone_targets'] += 1
                    
                    if play.get('complete_pass') == 1:
                        s['receptions'] += 1
                        s['receiving_yards'] += play.get('receiving_yards', 0)
                        
                    if play.get('touchdown') == 1 and play.get('td_team') == posteam:
                        s['receiving_tds'] += 1
                        if is_red_zone: s['red_zone_receiving_tds'] += 1

        # Process Rushing
        if play['play_type'] == 'run':
            rusher_id = play.get('rusher_player_id')
            rusher_name = play.get('rusher')
            posteam = play.get('posteam')
            db_posteam = get_db_team_abbr(posteam)
            
            # Team Stats
            ts = get_team_stats_entry(game_id, db_posteam)
            ts['rush_attempts'] += 1
            ts['total_yards'] += play.get('yards_gained', 0)
            if play.get('fumble_lost', 0) == 1:
                ts['turnovers'] += 1
            
            if rusher_id or rusher_name:
                pid = resolve_player(rusher_id, rusher_name, posteam)
                if pid:
                    s = get_stats_entry(game_id, pid, db_posteam)
                    if play.get('rush_attempt') == 1:
                        s['rush_attempts'] += 1
                        if is_red_zone: s['red_zone_rush_attempts'] += 1
                        
                    s['rushing_yards'] += play.get('rushing_yards', 0)
                    
                    if play.get('touchdown') == 1 and play.get('td_team') == posteam:
                        s['rushing_tds'] += 1
                        if is_red_zone: s['red_zone_rushing_tds'] += 1
                        
        processed_plays += 1

    logger.info(f"Processed {processed_plays} plays. Updating database...")
    
    from app.models.models import TeamGameOffenseStats
    
    # Batch Update/Create Team Stats
    for (game_id, team_abbr), stats in team_game_stats.items():
        # Need to find team ID
        # We can query game to get home/away team IDs
        # Or use team_id_map
        team_id = team_id_map.get(team_abbr)
        if not team_id: continue
        
        # Get Game info for season/week
        game = db.query(Game).get(game_id)
        
        tgos = db.query(TeamGameOffenseStats).filter(
            TeamGameOffenseStats.team_id == team_id,
            TeamGameOffenseStats.game_id == game_id
        ).first()
        
        if not tgos:
            tgos = TeamGameOffenseStats(
                team_id=team_id,
                game_id=game_id,
                season=game.season,
                week=game.week,
                team_name=team_abbr # Assuming team_name is abbr
            )
            db.add(tgos)
            
        tgos.pass_attempts = stats['pass_attempts']
        tgos.rush_attempts = stats['rush_attempts']
        tgos.total_yards = stats['total_yards']
        tgos.turnovers = stats['turnovers']
    
    # Batch Update/Create Player Stats
    for (game_id, player_id), stats in player_game_stats.items():
        pgs = db.query(PlayerGameStats).filter(
            PlayerGameStats.player_id == player_id,
            PlayerGameStats.game_id == game_id
        ).first()
        
        if not pgs:
            game = db.query(Game).get(game_id)
            team_id = team_id_map.get(stats['team_abbr'])
            
            if not team_id:
                continue
                
            pgs = PlayerGameStats(
                player_id=player_id,
                game_id=game_id,
                season=game.season,
                week=game.week,
                team=stats['team_abbr']
            )
            db.add(pgs)
        
        # Update Stats
        pgs.pass_attempts = stats['pass_attempts']
        pgs.pass_completions = stats['pass_completions']
        pgs.passing_yards = stats['passing_yards']
        pgs.passing_tds = stats['passing_tds']
        pgs.interceptions = stats['interceptions']
        
        pgs.rush_attempts = stats['rush_attempts']
        pgs.rushing_yards = stats['rushing_yards']
        pgs.rushing_tds = stats['rushing_tds']
        
        pgs.targets = stats['targets']
        pgs.receptions = stats['receptions']
        pgs.receiving_yards = stats['receiving_yards']
        pgs.receiving_tds = stats['receiving_tds']
        
        pgs.red_zone_pass_attempts = stats['red_zone_pass_attempts']
        pgs.red_zone_rush_attempts = stats['red_zone_rush_attempts']
        pgs.red_zone_targets = stats['red_zone_targets']
        pgs.red_zone_passing_tds = stats['red_zone_passing_tds']
        pgs.red_zone_rushing_tds = stats['red_zone_rushing_tds']
        pgs.red_zone_receiving_tds = stats['red_zone_receiving_tds']
        
        # Calculate Fantasy Points
        # Standard: 1 pt per 10 rush/rec yds, 1 pt per 25 pass yds, 6 pts TD, -2 INT, -2 Fumble
        # PPR: +1 per reception
        
        rush_pts = (stats['rushing_yards'] / 10.0) + (stats['rushing_tds'] * 6)
        rec_pts = (stats['receiving_yards'] / 10.0) + (stats['receiving_tds'] * 6)
        pass_pts = (stats['passing_yards'] / 25.0) + (stats['passing_tds'] * 4) - (stats['interceptions'] * 2)
        
        pgs.fantasy_points_standard = rush_pts + rec_pts + pass_pts
        pgs.fantasy_points_ppr = pgs.fantasy_points_standard + stats['receptions']
    
    db.commit()
    logger.info("Ingestion complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2025)
    args = parser.parse_args()
    
    ingest_pbp_data(args.year)
