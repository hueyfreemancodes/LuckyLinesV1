
import sys
import os
import logging
import pandas as pd
from collections import defaultdict
from app.core.database import SessionLocal
from app.models.models import Player, Game, Team, PlayerGameStats, TeamGameOffenseStats

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEAM_MAPPING = {
    'JAX': 'JAC', 'LAC': 'LOS', 'LAR': 'LOS', 'LV': 'LAS',
    'NE': 'NEW', 'NO': 'NEW', 'NYJ': 'NEW', 'NYG': 'NEW',
    'GB': 'GRE', 'TB': 'TAM', 'SF': 'SF', 'KC': 'KAN', 'WSH': 'WAS'
}

def get_db_team_abbr(nfl_abbr):
    return TEAM_MAPPING.get(nfl_abbr, nfl_abbr)

def ingest_pbp_data(year: int = 2025):
    """Ingest PBP data from NFLverse for the specified year."""
    db = SessionLocal()
    
    logger.info(f"Fetching PBP data for {year} from NFLverse...")
    try:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet"
        pbp = pd.read_parquet(url)
    except Exception as e:
        logger.error(f"Failed to fetch PBP data: {e}")
        return

    # Filter for Pass/Run in Regular Season
    plays = pbp[
        (pbp['play_type'].isin(['pass', 'run'])) &
        (pbp['season_type'] == 'REG')
    ]
    logger.info(f"Processing {len(plays)} plays...")

    # --- Pre-Fetch Lookups ---
    # GSIS Map
    players = db.query(Player).all()
    gsis_map = {p.external_ids['gsis']: p.id for p in players if p.external_ids and 'gsis' in p.external_ids}
    
    # Fuzzy Map (F.Lastname, Team)
    f_last_map = {}
    for p in players:
        if p.team and p.first_name and p.last_name:
            key = (f"{p.first_name[0]}.{p.last_name}".upper(), p.team.abbreviation)
            f_last_map[key] = p.id
            
    # Game Map
    games = db.query(Game).filter(Game.season == year).all()
    game_map = {(g.week, g.home_team.abbreviation, g.away_team.abbreviation): g.id for g in games if g.home_team and g.away_team}
    
    # Team Map
    teams = db.query(Team).all()
    team_id_map = {t.abbreviation: t.id for t in teams}

    # --- Aggregation ---
    # Key: (game_id, player_id) -> Stats Dict
    player_stats = defaultdict(lambda: defaultdict(int)) # Nested int dict for easy += 1
    # Key: (game_id, team_abbr) -> Stats Dict
    team_stats = defaultdict(lambda: defaultdict(int))
    
    def resolve_player(pid, name, team):
        if pid in gsis_map: return gsis_map[pid]
        db_team = get_db_team_abbr(team)
        if name and db_team:
            return f_last_map.get((name.upper(), db_team))
        return None

    # --- Processing Loop ---
    for _, play in plays.iterrows():
        week = play['week']
        home, away = get_db_team_abbr(play['home_team']), get_db_team_abbr(play['away_team'])
        
        game_id = game_map.get((week, home, away))
        if not game_id: continue

        posteam = play.get('posteam')
        db_posteam = get_db_team_abbr(posteam)
        is_rz = (play['yardline_100'] <= 20)
        
        # Team Stats Update
        ts = team_stats[(game_id, db_posteam)]
        ts['total_yards'] += play.get('yards_gained', 0)
        if play.get('interception') == 1 or play.get('fumble_lost') == 1:
            ts['turnovers'] += 1

        # Play Logic
        ptype = play['play_type']
        
        if ptype == 'pass':
            ts['pass_attempts'] += 1
            
            # Passer
            pid = resolve_player(play.get('passer_player_id'), play.get('passer'), posteam)
            if pid:
                s = player_stats[(game_id, pid)]
                s['team_abbr'] = db_posteam
                s['passing_yards'] += play.get('yards_gained', 0)
                if play.get('pass_attempt') == 1:
                    s['pass_attempts'] += 1
                    if is_rz: s['rz_pass_att'] += 1
                if play.get('complete_pass') == 1:
                    s['pass_comp'] += 1
                if play.get('touchdown') == 1 and play.get('td_team') == posteam:
                    s['pass_td'] += 1
                    if is_rz: s['rz_pass_td'] += 1
                if play.get('interception') == 1:
                    s['int'] += 1

            # Receiver
            rid = resolve_player(play.get('receiver_player_id'), play.get('receiver'), posteam)
            if rid:
                s = player_stats[(game_id, rid)]
                s['team_abbr'] = db_posteam
                s['targets'] += 1
                if is_rz: s['rz_target'] += 1
                if play.get('complete_pass') == 1:
                    s['rec'] += 1
                    s['rec_yds'] += play.get('receiving_yards', 0)
                if play.get('touchdown') == 1 and play.get('td_team') == posteam:
                    s['rec_td'] += 1
                    if is_rz: s['rz_rec_td'] += 1

        elif ptype == 'run':
            ts['rush_attempts'] += 1
            
            # Rusher
            rid = resolve_player(play.get('rusher_player_id'), play.get('rusher'), posteam)
            if rid:
                s = player_stats[(game_id, rid)]
                s['team_abbr'] = db_posteam
                s['rush_att'] += 1
                s['rush_yds'] += play.get('rushing_yards', 0)
                if is_rz: s['rz_rush_att'] += 1
                if play.get('touchdown') == 1 and play.get('td_team') == posteam:
                    s['rush_td'] += 1
                    if is_rz: s['rz_rush_td'] += 1

    # --- Database Update ---
    logger.info("Updating database...")
    
    # Team Stats
    for (gid, team_abbr), stats in team_stats.items():
        tid = team_id_map.get(team_abbr)
        if not tid: continue
        
        tgos = db.query(TeamGameOffenseStats).filter_by(team_id=tid, game_id=gid).first()
        if not tgos:
            # Need season/week from games dict? We only stored IDs.
            # Re-querying per team is okay, or optimized:
             # We passed `year` as arg, so season is known. Week? We handled (Season, Week, Home, Away) -> GID
             # We can assume game data exists.
             # Ideally we cache Game info too.
             pass # MVP: Skipping create if not exists for brevity or add robust logic.
             # Actually, let's create it.
             game = db.query(Game).get(gid)
             tgos = TeamGameOffenseStats(team_id=tid, game_id=gid, season=game.season, week=game.week, team_name=team_abbr)
             db.add(tgos)
             
        tgos.pass_attempts = stats['pass_attempts']
        tgos.rush_attempts = stats['rush_attempts']
        tgos.total_yards = stats['total_yards']
        tgos.turnovers = stats['turnovers']

    # Player Stats
    for (gid, pid), stats in player_stats.items():
        pgs = db.query(PlayerGameStats).filter_by(player_id=pid, game_id=gid).first()
        if not pgs:
            game = db.query(Game).get(gid)
            pgs = PlayerGameStats(player_id=pid, game_id=gid, season=game.season, week=game.week, team=stats['team_abbr'])
            db.add(pgs)

        # Assign Map
        pgs.pass_attempts = stats['pass_attempts']
        pgs.pass_completions = stats['pass_comp']
        pgs.passing_yards = stats['passing_yards']
        pgs.passing_tds = stats['pass_td']
        pgs.interceptions = stats['int']
        pgs.rush_attempts = stats['rush_att']
        pgs.rushing_yards = stats['rush_yds']
        pgs.rushing_tds = stats['rush_td']
        pgs.targets = stats['targets']
        pgs.receptions = stats['rec']
        pgs.receiving_yards = stats['rec_yds']
        pgs.receiving_tds = stats['rec_td']
        
        # RZ
        pgs.red_zone_pass_attempts = stats['rz_pass_att']
        pgs.red_zone_rush_attempts = stats['rz_rush_att']
        pgs.red_zone_targets = stats['rz_target']
        pgs.red_zone_passing_tds = stats['rz_pass_td']
        pgs.red_zone_rushing_tds = stats['rz_rush_td']
        pgs.red_zone_receiving_tds = stats['rz_rec_td']
        
        # Calc Points
        pgs.fantasy_points_standard = (pgs.rushing_yards / 10) + (pgs.rushing_tds * 6) + \
                                      (pgs.receiving_yards / 10) + (pgs.receiving_tds * 6) + \
                                      (pgs.passing_yards / 25) + (pgs.passing_tds * 4) - (pgs.interceptions * 2)
        pgs.fantasy_points_ppr = pgs.fantasy_points_standard + pgs.receptions

    db.commit()
    logger.info("Done.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2025)
    args = parser.parse_args()
    ingest_pbp_data(args.year)
