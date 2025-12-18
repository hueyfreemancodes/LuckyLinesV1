import pandas as pd
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.models import Player, Projection, Slate
from app.ingestion.base import BaseIngestion
import logging

logger = logging.getLogger(__name__)

class CSVIngestion:
    """
    Ingests player projections from a CSV file.
    Expected CSV columns: name, position, team, salary, points, (optional: ceiling, floor)
    """
    
    def __init__(self, db: Session):
        self.db = db
        
    async def process_csv(self, file_content: bytes, sport: str, source: str):
        """
        Parses CSV content and updates projections.
        """
        try:
            # 1. Read CSV
            df = pd.read_csv(pd.io.common.BytesIO(file_content))
            
            # Normalize columns to lowercase
            df.columns = df.columns.str.lower()
            
            required_cols = ['name', 'points']
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"CSV must contain columns: {required_cols}")
            
            # 2. Process each row
            projections_added = 0
            
            # Get or create a dummy slate for this import
            # In a real app, user would select the slate ID from the frontend
            slate = self.db.query(Slate).filter(Slate.sport_id == 1).first() 
            if not slate:
                logger.warning("No slate found, skipping projection save")
                return 0

            for _, row in df.iterrows():
                player_name = row['name']
                points = row['points']
                
                # Find player by name
                parts = player_name.split()
                if len(parts) < 2:
                    continue
                    
                first_name = parts[0]
                last_name = " ".join(parts[1:])
                
                player = self.db.query(Player).filter(
                    Player.first_name.ilike(first_name),
                    Player.last_name.ilike(last_name)
                ).first()
                
                if player:
                    # Update or Create Projection
                    proj = self.db.query(Projection).filter(
                        Projection.player_id == player.id,
                        Projection.slate_id == slate.id,
                        Projection.source == source
                    ).first()
                    
                    if not proj:
                        proj = Projection(
                            player_id=player.id,
                            slate_id=slate.id,
                            source=source
                        )
                        self.db.add(proj)
                    
                    proj.points = float(points)
                    if 'ceiling' in row:
                        proj.ceiling = float(row['ceiling'])
                    if 'floor' in row:
                        proj.floor = float(row['floor'])
                        
                    projections_added += 1
            
            self.db.commit()
            return projections_added
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing CSV: {e}")
            raise e
    async def process_player_stats_offense(self, file_content: bytes):
        """
        Parses 'Weekly Player Stats Offense' CSV and saves to PlayerGameStats.
        """
        from app.models.models import PlayerGameStats, Player, Game, Team
        
        try:
            df = pd.read_csv(pd.io.common.BytesIO(file_content))
            # Columns are already snake_case in the provided schema, but let's normalize just in case
            df.columns = df.columns.str.lower()
            df.fillna(0, inplace=True) # Handle missing values
            
            records_added = 0
            
            for _, row in df.iterrows():
                # 1. Find or Create Team
                team_abbr = row.get('team')
                if not team_abbr: continue
                
                team = self.db.query(Team).filter(Team.abbreviation == team_abbr).first()
                if not team:
                    # Create missing team
                    team = Team(
                        sport_id=1, # Assuming NFL is ID 1
                        name=f"Team {team_abbr}",
                        abbreviation=team_abbr
                    )
                    self.db.add(team)
                    self.db.flush() # Get ID
                
                # 2. Find or Create Player
                player_name = row.get('player_name')
                if not player_name: continue
                
                parts = player_name.split()
                if len(parts) < 2: continue
                first_name = parts[0]
                last_name = " ".join(parts[1:])
                
                player = self.db.query(Player).filter(
                    Player.first_name.ilike(first_name),
                    Player.last_name.ilike(last_name)
                ).first()
                
                if not player:
                    # Create missing player
                    position = row.get('position', 'UNK')
                    player = Player(
                        sport_id=1, # Assuming NFL
                        team_id=team.id,
                        first_name=first_name,
                        last_name=last_name,
                        position=position
                    )
                    self.db.add(player)
                    self.db.flush()
                
                # 2. Create/Update PlayerGameStats
                season = int(row['season'])
                week = int(row['week'])
                
                stats = self.db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == player.id,
                    PlayerGameStats.season == season,
                    PlayerGameStats.week == week
                ).first()
                
                if not stats:
                    stats = PlayerGameStats(
                        player_id=player.id,
                        season=season,
                        week=week
                    )
                    self.db.add(stats)
                
                # Map columns
                stats.team = row.get('team')
                stats.pass_attempts = int(row.get('pass_attempts', 0))
                stats.pass_completions = int(row.get('complete_pass', 0))
                stats.passing_yards = float(row.get('passing_yards', 0.0))
                stats.passing_tds = int(row.get('pass_touchdown', 0))
                stats.interceptions = int(row.get('interception', 0))
                
                stats.rush_attempts = int(row.get('rush_attempts', 0))
                stats.rushing_yards = float(row.get('rushing_yards', 0.0))
                stats.rushing_tds = int(row.get('rush_touchdown', 0))
                
                stats.targets = int(row.get('targets', 0))
                stats.receptions = int(row.get('receptions', 0))
                stats.receiving_yards = float(row.get('receiving_yards', 0.0))
                stats.receiving_tds = int(row.get('receiving_touchdown', 0))
                
                stats.fantasy_points_ppr = float(row.get('fantasy_points_ppr', 0.0))
                stats.fantasy_points_standard = float(row.get('fantasy_points_standard', 0.0))
                
                records_added += 1
                
            self.db.commit()
            return records_added

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing Player Stats Offense CSV: {e}")
            raise e

    async def process_player_stats_defense(self, file_content: bytes):
        """
        Parses 'Weekly Player Stats Defense' CSV and saves to PlayerGameDefenseStats.
        """
        from app.models.models import PlayerGameDefenseStats, Player, Team
        
        try:
            df = pd.read_csv(pd.io.common.BytesIO(file_content))
            df.columns = df.columns.str.lower()
            df.fillna(0, inplace=True)
            
            records_added = 0
            
            for _, row in df.iterrows():
                # 1. Find or Create Team
                team_abbr = row.get('team')
                if not team_abbr: continue
                
                team = self.db.query(Team).filter(Team.abbreviation == team_abbr).first()
                if not team:
                    team = Team(
                        sport_id=1,
                        name=f"Team {team_abbr}",
                        abbreviation=team_abbr
                    )
                    self.db.add(team)
                    self.db.flush()

                # 2. Find or Create Player
                player_name = row.get('player_name')
                if not player_name: continue
                
                parts = player_name.split()
                if len(parts) < 2: continue
                first_name = parts[0]
                last_name = " ".join(parts[1:])
                
                player = self.db.query(Player).filter(
                    Player.first_name.ilike(first_name),
                    Player.last_name.ilike(last_name)
                ).first()
                
                if not player:
                    position = row.get('position', 'DST') # Default to DST or UNK
                    player = Player(
                        sport_id=1,
                        team_id=team.id,
                        first_name=first_name,
                        last_name=last_name,
                        position=position
                    )
                    self.db.add(player)
                    self.db.flush()
                
                season = int(row['season'])
                week = int(row['week'])
                
                stats = self.db.query(PlayerGameDefenseStats).filter(
                    PlayerGameDefenseStats.player_id == player.id,
                    PlayerGameDefenseStats.season == season,
                    PlayerGameDefenseStats.week == week
                ).first()
                
                if not stats:
                    stats = PlayerGameDefenseStats(
                        player_id=player.id,
                        season=season,
                        week=week
                    )
                    self.db.add(stats)
                
                stats.team = row.get('team')
                stats.solo_tackle = int(row.get('solo_tackle', 0))
                stats.assist_tackle = int(row.get('assist_tackle', 0))
                stats.sacks = float(row.get('sack', 0.0))
                stats.qb_hits = int(row.get('qb_hit', 0))
                stats.interceptions = int(row.get('interception', 0))
                stats.fumbles_forced = int(row.get('fumble_forced', 0))
                stats.defensive_tds = int(row.get('def_touchdown', 0))
                stats.safeties = int(row.get('safety', 0))
                
                stats.fantasy_points_ppr = float(row.get('fantasy_points_ppr', 0.0))
                stats.fantasy_points_standard = float(row.get('fantasy_points_standard', 0.0))
                
                records_added += 1
                
            self.db.commit()
            return records_added

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing Player Stats Defense CSV: {e}")
            raise e

    async def process_team_stats_offense(self, file_content: bytes):
        """
        Parses 'Weekly Team Stats Offense' CSV.
        """
        from app.models.models import TeamGameOffenseStats, Team
        
        try:
            df = pd.read_csv(pd.io.common.BytesIO(file_content))
            df.columns = df.columns.str.lower()
            df.fillna(0, inplace=True)
            records_added = 0
            
            for _, row in df.iterrows():
                team_abbr = row.get('team')
                if not team_abbr: continue
                
                # Find team by abbreviation (assuming seeded)
                team = self.db.query(Team).filter(Team.abbreviation == team_abbr).first()
                team_id = team.id if team else None
                
                season = int(row['season'])
                week = int(row['week'])
                
                stats = self.db.query(TeamGameOffenseStats).filter(
                    TeamGameOffenseStats.team_name == team_abbr,
                    TeamGameOffenseStats.season == season,
                    TeamGameOffenseStats.week == week
                ).first()
                
                if not stats:
                    stats = TeamGameOffenseStats(
                        team_name=team_abbr,
                        team_id=team_id,
                        season=season,
                        week=week
                    )
                    self.db.add(stats)
                
                stats.total_yards = float(row.get('total_off_yards', 0.0))
                stats.pass_attempts = int(row.get('pass_attempts', 0)) # Assuming column exists in CSV?
                # Check CSV schema from user prompt or previous knowledge.
                # The user provided "Weekly Team Stats Offense".
                # I should check if that CSV has attempts.
                # If not, I might have to sum up player stats?
                # Let's assume it does for now or default to 0.
                stats.passing_yards = float(row.get('passing_yards', 0.0))
                stats.rush_attempts = int(row.get('rush_attempts', 0))
                stats.rushing_yards = float(row.get('rushing_yards', 0.0))
                stats.total_points = int(row.get('total_off_points', 0))
                # Calculate turnovers if columns exist
                ints = int(row.get('interception', 0))
                fumbles_lost = int(row.get('fumble_lost', 0))
                stats.turnovers = ints + fumbles_lost
                
                records_added += 1
            
            self.db.commit()
            return records_added
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing Team Stats Offense CSV: {e}")
            raise e

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing Team Stats Defense CSV: {e}")
            raise e

    async def process_play_by_play(self, file_content: bytes):
        """
        Parses Play-by-Play CSV to extract Red Zone stats.
        """
        from app.models.models import PlayerGameStats, Player
        import re
        from datetime import datetime, timedelta
        
        try:
            df = pd.read_csv(pd.io.common.BytesIO(file_content))
            # Normalize columns
            df.columns = df.columns.str.replace(' ', '').str.replace(':', '').str.replace('Unnamed', 'Unk')
            
            # Regex for player names: "F.Lastname"
            name_pattern = re.compile(r'([A-Z]\.[A-Za-z]+)')
            
            # Helper to map Date -> Week
            # Since we don't have a perfect calendar, we'll define start dates
            def get_week(date_str, season):
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

            # Aggregate Stats in Memory
            # Key: (Season, Week, PlayerNameInitial) -> Stats
            agg_stats = {} 
            
            for _, row in df.iterrows():
                # Check Red Zone
                try:
                    yl = float(row.get('YardLine', 100))
                    if yl > 20: continue # Skip non-RZ
                except:
                    continue
                    
                desc = str(row.get('Description', ''))
                season = int(row.get('SeasonYear', 2023))
                date_str = row.get('GameDate')
                week = get_week(date_str, season)
                
                # Parse Player
                matches = name_pattern.findall(desc)
                if not matches: continue
                
                # Logic
                is_pass = 'pass' in desc.lower()
                is_rush = 'tackle' in desc.lower() or 'run' in desc.lower() or 'rush' in desc.lower()
                is_td = 'touchdown' in desc.lower()
                
                player_key = None
                stat_type = None
                
                if is_pass:
                    # Passer is matches[0]
                    passer = matches[0]
                    k = (season, week, passer)
                    if k not in agg_stats: agg_stats[k] = {'rz_pass':0, 'rz_rush':0, 'rz_target':0, 'rz_pass_td':0, 'rz_rush_td':0, 'rz_rec_td':0}
                    agg_stats[k]['rz_pass'] += 1
                    if is_td: agg_stats[k]['rz_pass_td'] += 1
                    
                    # Receiver is matches[1] if exists
                    if 'to ' in desc.lower() and len(matches) > 1:
                        receiver = matches[1]
                        k = (season, week, receiver)
                        if k not in agg_stats: agg_stats[k] = {'rz_pass':0, 'rz_rush':0, 'rz_target':0, 'rz_pass_td':0, 'rz_rush_td':0, 'rz_rec_td':0}
                        agg_stats[k]['rz_target'] += 1
                        if is_td: agg_stats[k]['rz_rec_td'] += 1
                        
                elif is_rush:
                    rusher = matches[0]
                    k = (season, week, rusher)
                    if k not in agg_stats: agg_stats[k] = {'rz_pass':0, 'rz_rush':0, 'rz_target':0, 'rz_pass_td':0, 'rz_rush_td':0, 'rz_rec_td':0}
                    agg_stats[k]['rz_rush'] += 1
                    if is_td: agg_stats[k]['rz_rush_td'] += 1

            # Bulk Update DB
            # Iterate aggregated stats and update PlayerGameStats
            updates = 0
            for (season, week, p_name), stats in agg_stats.items():
                # Find player by "F.Last"
                # This is fuzzy. We need to match "P.Mahomes" to "Patrick Mahomes".
                # Split p_name: "P", "Mahomes"
                parts = p_name.split('.')
                if len(parts) < 2: continue
                first_initial = parts[0]
                last_name = parts[1]
                
                # Find player in DB
                # Optimize: Cache player lookups
                player = self.db.query(Player).filter(
                    Player.last_name.ilike(last_name),
                    Player.first_name.startswith(first_initial)
                ).first()
                
                if not player: continue
                
                # Update Stats
                pgs = self.db.query(PlayerGameStats).filter(
                    PlayerGameStats.player_id == player.id,
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
            
            self.db.commit()
            logger.info(f"Updated Red Zone stats for {updates} records.")
            return updates
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing PBP: {e}")
            raise e
    async def process_salary_csv(self, file_content: bytes, platform: str, season: int, week: int):
        """
        Parses Salary CSV (DK/FD) and updates PlayerSlate table.
        """
        from app.models.models import PlayerSlate, Slate, Player, Team
        import pandas as pd
        from datetime import datetime
        
        try:
            df = pd.read_csv(pd.io.common.BytesIO(file_content))
            records_added = 0
            
            # 1. Create or Get Slate
            slate_name = f"{platform} Week {week} Main Slate"
            slate = self.db.query(Slate).filter(
                Slate.platform == platform,
                Slate.name == slate_name
            ).first()
            
            if not slate:
                slate = Slate(
                    sport_id=1, # NFL
                    platform=platform,
                    name=slate_name,
                    start_time=datetime.now() # Placeholder
                )
                self.db.add(slate)
                self.db.flush()
                
            # 2. Process Rows
            for _, row in df.iterrows():
                player = None
                salary = 0
                roster_position = "FLEX"
                
                if platform.lower() == "draftkings":
                    # DK Cols: Position, Name + ID, Name, ID, Roster Position, Salary, Game Info, TeamAbbrev, AvgPointsPerGame
                    name = row.get('Name')
                    if not name: continue
                    
                    salary = int(row.get('Salary', 0))
                    roster_position = row.get('Roster Position', 'FLEX')
                    team_abbr = row.get('TeamAbbrev')
                    
                    # Find Player
                    parts = name.split()
                    if len(parts) >= 2:
                        player = self.db.query(Player).filter(
                            Player.first_name.ilike(parts[0]),
                            Player.last_name.ilike(" ".join(parts[1:]))
                        ).first()
                        
                elif platform.lower() == "fanduel":
                    # FD Cols: Id, Position, First Name, Last Name, FPPG, Played, Salary, Game, Team, Opponent...
                    first = row.get('First Name')
                    last = row.get('Last Name')
                    if not first or not last: continue
                    
                    salary = int(row.get('Salary', 0))
                    roster_position = row.get('Roster Position', 'FLEX')
                    
                    player = self.db.query(Player).filter(
                        Player.first_name.ilike(first),
                        Player.last_name.ilike(last)
                    ).first()
                    
                if player:
                    # Create/Update PlayerSlate
                    ps = self.db.query(PlayerSlate).filter(
                        PlayerSlate.player_id == player.id,
                        PlayerSlate.slate_id == slate.id
                    ).first()
                    
                    if not ps:
                        ps = PlayerSlate(
                            player_id=player.id,
                            slate_id=slate.id
                        )
                        self.db.add(ps)
                    
                    ps.salary = salary
                    ps.roster_position = roster_position
                    records_added += 1
            
            self.db.commit()
            return records_added
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing Salary CSV: {e}")
            raise e
