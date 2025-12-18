import pandas as pd
import logging
from sqlalchemy.orm import Session
from app.models.models import Player, Projection, Slate, PlayerGameStats, Team, PlayerGameDefenseStats, TeamGameOffenseStats, PlayerSlate
from datetime import datetime

logger = logging.getLogger(__name__)

class CSVIngestion:
    """Service for ingesting various CSV data feeds."""
    
    def __init__(self, db: Session):
        self.db = db
        
    def _read_csv(self, content: bytes) -> pd.DataFrame:
        df = pd.read_csv(pd.io.common.BytesIO(content))
        df.columns = df.columns.str.lower().str.replace(' ', '_')
        return df.fillna(0)

    def _get_or_create_team(self, abbr):
        if not abbr: return None
        team = self.db.query(Team).filter_by(abbreviation=abbr).first()
        if not team:
            team = Team(sport_id=1, name=f"Team {abbr}", abbreviation=abbr)
            self.db.add(team)
            self.db.flush()
        return team

    def _get_or_create_player(self, name_str, team_id, position='UNK'):
        parts = name_str.split()
        if len(parts) < 2: return None
        
        first, last = parts[0], " ".join(parts[1:])
        player = self.db.query(Player).filter(
            Player.first_name.ilike(first), 
            Player.last_name.ilike(last)
        ).first()
        
        if not player:
            player = Player(sport_id=1, team_id=team_id, first_name=first, last_name=last, position=position)
            self.db.add(player)
            self.db.flush()
        return player

    def process_csv(self, file_content: bytes, sport: str, source: str):
        """Process Player Projections."""
        df = self._read_csv(file_content)
        slate = self.db.query(Slate).filter_by(sport_id=1).first()
        if not slate: return 0

        count = 0
        for _, row in df.iterrows():
            # Simplify name finding
            parts = str(row.get('name', '')).split()
            if len(parts) < 2: continue
            
            p = self.db.query(Player).filter(
                Player.first_name.ilike(parts[0]), 
                Player.last_name.ilike(" ".join(parts[1:]))
            ).first()
            
            if p:
                proj = self.db.query(Projection).filter_by(player_id=p.id, slate_id=slate.id, source=source).first()
                if not proj:
                    proj = Projection(player_id=p.id, slate_id=slate.id, source=source)
                    self.db.add(proj)
                
                proj.points = float(row.get('points', 0))
                if 'ceiling' in row: proj.ceiling = float(row['ceiling'])
                if 'floor' in row: proj.floor = float(row['floor'])
                count += 1
                
        self.db.commit()
        return count

    def process_player_stats_offense(self, file_content: bytes):
        df = self._read_csv(file_content)
        count = 0
        
        for _, row in df.iterrows():
            team = self._get_or_create_team(row.get('team'))
            if not team: continue
            
            player = self._get_or_create_player(row.get('player_name'), team.id, row.get('position', 'UNK'))
            if not player: continue
            
            season, week = int(row['season']), int(row['week'])
            stats = self.db.query(PlayerGameStats).filter_by(player_id=player.id, season=season, week=week).first()
            
            if not stats:
                stats = PlayerGameStats(player_id=player.id, season=season, week=week)
                self.db.add(stats)
            
            # Map Stats
            stats.team = team.abbreviation
            stats.pass_attempts = int(row.get('pass_attempts', 0))
            stats.pass_completions = int(row.get('complete_pass', 0))
            stats.passing_yards = float(row.get('passing_yards', 0))
            stats.passing_tds = int(row.get('pass_touchdown', 0))
            stats.interceptions = int(row.get('interception', 0))
            stats.rush_attempts = int(row.get('rush_attempts', 0))
            stats.rushing_yards = float(row.get('rushing_yards', 0))
            stats.rushing_tds = int(row.get('rush_touchdown', 0))
            stats.targets = int(row.get('targets', 0))
            stats.receptions = int(row.get('receptions', 0))
            stats.receiving_yards = float(row.get('receiving_yards', 0))
            stats.receiving_tds = int(row.get('receiving_touchdown', 0))
            stats.fantasy_points_ppr = float(row.get('fantasy_points_ppr', 0))
            stats.fantasy_points_standard = float(row.get('fantasy_points_standard', 0))
            count += 1
            
        self.db.commit()
        return count

    def process_player_stats_defense(self, file_content: bytes):
        df = self._read_csv(file_content)
        count = 0
        
        for _, row in df.iterrows():
            team = self._get_or_create_team(row.get('team'))
            if not team: continue # Must have team
            
            player = self._get_or_create_player(row.get('player_name'), team.id, 'DST')
            if not player: continue
            
            season, week = int(row['season']), int(row['week'])
            stats = self.db.query(PlayerGameDefenseStats).filter_by(player_id=player.id, season=season, week=week).first()
            if not stats:
                stats = PlayerGameDefenseStats(player_id=player.id, season=season, week=week)
                self.db.add(stats)
                
            stats.team = team.abbreviation
            stats.sacks = float(row.get('sack', 0))
            stats.interceptions = int(row.get('interception', 0))
            stats.fumbles_forced = int(row.get('fumble_forced', 0))
            stats.defensive_tds = int(row.get('def_touchdown', 0))
            stats.fantasy_points_ppr = float(row.get('fantasy_points_ppr', 0))
            count += 1
            
        self.db.commit()
        return count

    def process_salary_csv(self, content: bytes, platform: str, season: int, week: int):
        df = self._read_csv(content)
        slate_name = f"{platform} Week {week} Main Slate"
        slate = self.db.query(Slate).filter_by(platform=platform, name=slate_name).first()
        
        if not slate:
            slate = Slate(sport_id=1, platform=platform, name=slate_name, start_time=datetime.now())
            self.db.add(slate)
            self.db.flush()
            
        count = 0
        for _, row in df.iterrows():
            name = row.get('name') or (row.get('first_name') + ' ' + row.get('last_name'))
            if not name: continue
            
            parts = str(name).split()
            if len(parts) < 2: continue
            
            p = self.db.query(Player).filter(
                Player.first_name.ilike(parts[0]),
                Player.last_name.ilike(" ".join(parts[1:]))
            ).first()
            
            if p:
                ps = self.db.query(PlayerSlate).filter_by(player_id=p.id, slate_id=slate.id).first()
                if not ps:
                    ps = PlayerSlate(player_id=p.id, slate_id=slate.id)
                    self.db.add(ps)
                
                ps.salary = int(row.get('salary', 0))
                ps.roster_position = row.get('roster_position', 'FLEX')
                count += 1
                
        self.db.commit()
        return count
