import requests
from typing import Any, Dict, List, Optional
import os
from .base import BaseIngestion
from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, Player, Team

class SportsDataIOIngestion(BaseIngestion):
    """
    Ingests Player Game Stats from SportsDataIO API.
    """
    
    BASE_URL = "https://api.sportsdata.io/v3/nfl/stats/json/PlayerGameStatsByWeek"
    API_KEY = "9f52850ed5494c11ae371312e036e97b" 

    def __init__(self):
        super().__init__("SportsDataIO-PlayerStats")
        self.db = SessionLocal()

    async def fetch(self, season: int = 2025, week: int = 1) -> Any:
        """
        Fetch stats for a specific season and week.
        """
        url = f"{self.BASE_URL}/{season}/{week}?key={self.API_KEY}"
        self.logger.info(f"Fetching stats from: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching data: {e}")
            return []

    async def transform(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Transform API response to match PlayerGameStats model.
        """
        transformed = []
        
        # Pre-fetch lookups to minimize DB hits
        players = self.db.query(Player).all()
        # Create lookup map: { "first last": id, "last": id }
        player_map = {}
        for p in players:
            full_name = f"{p.first_name} {p.last_name}".lower()
            player_map[full_name] = p.id
            # Also map by SportsDataIO PlayerID if we had it stored, but we don't yet.
            # We rely on name matching for now.
            
        teams = self.db.query(Team).all()
        team_map = {t.abbreviation: t.id for t in teams}
        
        for item in raw_data:
            # Skip players with no stats (optional, but good for noise reduction)
            if item.get('FantasyPoints', 0) == 0 and item.get('Played') != 1:
                continue
                
            player_name = item.get('Name')
            if not player_name:
                continue
                
            # Find Player ID
            player_id = player_map.get(player_name.lower())
            
            # If not found, try simple fuzzy logic (e.g. "Patrick Mahomes II" vs "Patrick Mahomes")
            if not player_id:
                # Try stripping suffixes
                clean_name = player_name.replace(" II", "").replace(" III", "").replace(" Jr.", "").replace(" Sr.", "")
                player_id = player_map.get(clean_name.lower())
                
            if not player_id:
                # Log warning but skip for now (or create?)
                # self.logger.warning(f"Player not found: {player_name}")
                continue
            
            # Map Stats
            stat = {
                "player_id": player_id,
                "season": item.get('Season'),
                "week": item.get('Week'),
                "team": item.get('Team'),
                "opponent": item.get('Opponent'),
                # "game_date": item.get('GameDate'), # Removed: Not in model
                
                # Passing
                "passing_yards": item.get('PassingYards', 0),
                "passing_tds": item.get('PassingTouchdowns', 0),
                "interceptions": item.get('PassingInterceptions', 0),
                "pass_attempts": item.get('PassingAttempts', 0),
                "pass_completions": item.get('PassingCompletions', 0),
                
                # Rushing
                "rushing_yards": item.get('RushingYards', 0),
                "rushing_tds": item.get('RushingTouchdowns', 0),
                "rush_attempts": item.get('RushingAttempts', 0),
                
                # Receiving
                "receiving_yards": item.get('ReceivingYards', 0),
                "receiving_tds": item.get('ReceivingTouchdowns', 0),
                "receptions": item.get('Receptions', 0),
                "targets": item.get('ReceivingTargets', 0),
                
                # Fantasy
                "fantasy_points_ppr": item.get('FantasyPointsPPR', 0),
                
                # Red Zone (SportsDataIO has specific fields? Need to check schema)
                # For now, standard stats
            }
            transformed.append(stat)
            
        return transformed

    async def load(self, data: List[Dict[str, Any]]) -> int:
        count = 0
        updated = 0
        
        for item in data:
            # Check if exists
            existing = self.db.query(PlayerGameStats).filter(
                PlayerGameStats.player_id == item['player_id'],
                PlayerGameStats.season == item['season'],
                PlayerGameStats.week == item['week']
            ).first()
            
            if existing:
                # Update
                for key, value in item.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                updated += 1
            else:
                # Create
                new_stat = PlayerGameStats(**item)
                self.db.add(new_stat)
                count += 1
                
            if (count + updated) % 100 == 0:
                self.db.commit()
                
        self.db.commit()
        self.logger.info(f"Loaded {count} new records, updated {updated} existing records.")
        return count + updated
