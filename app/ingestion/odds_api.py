import httpx
from typing import Any, Dict, List
import os
from .base import BaseIngestion

class OddsAPIIngestion(BaseIngestion):
    """
    Ingests Vegas lines from The Odds API.
    """
    
    BASE_URL = "https://api.the-odds-api.com/v4/sports"

    def __init__(self, sport: str = "americanfootball_nfl"):
        super().__init__(f"OddsAPI-{sport}")
        self.sport = sport
        self.api_key = os.getenv("ODDS_API_KEY")

    async def fetch(self, date: str = None) -> Any:
        if not self.api_key:
            self.logger.warning("ODDS_API_KEY not set, skipping fetch.")
            return []

        async with httpx.AsyncClient() as client:
            if date:
                # Historical Endpoint
                # https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds
                url = f"https://api.the-odds-api.com/v4/historical/sports/{self.sport}/odds"
                params = {
                    "apiKey": self.api_key,
                    "regions": "us",
                    "markets": "h2h,spreads,totals",
                    "oddsFormat": "american",
                    "date": date
                }
            else:
                # Live Endpoint
                url = f"{self.BASE_URL}/{self.sport}/odds"
                params = {
                    "apiKey": self.api_key,
                    "regions": "us",
                    "markets": "h2h,spreads,totals",
                    "oddsFormat": "american"
                }
                
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def transform(self, raw_data: Any) -> List[Dict[str, Any]]:
        # Historical response has a 'data' key, live response is a list directly
        games_list = raw_data.get('data', []) if isinstance(raw_data, dict) else raw_data
        
        transformed = []
        for game in games_list:
            transformed.append({
                "game_id": game.get("id"),
                "home_team": game.get("home_team"),
                "away_team": game.get("away_team"),
                "commence_time": game.get("commence_time"),
                "bookmakers": game.get("bookmakers", [])
            })
        return transformed

    async def load(self, data: List[Dict[str, Any]]) -> int:
        from app.models.models import VegasLine, Game, Team
        
        count = 0
        for item in data:
            # 1. Find or Create Game
            # Simplified matching: In production, use robust team name matching
            home_team_name = item['home_team']
            away_team_name = item['away_team']
            
            # Try to find teams (this assumes teams are already seeded/exist)
            home_team = self.db.query(Team).filter(Team.name.ilike(f"%{home_team_name}%")).first()
            away_team = self.db.query(Team).filter(Team.name.ilike(f"%{away_team_name}%")).first()
            
            if not home_team:
                print(f"Creating missing home team: '{home_team_name}'")
                home_team = Team(sport_id=1, name=home_team_name, abbreviation=home_team_name[:3].upper())
                self.db.add(home_team)
                self.db.flush() # Get ID
                
            if not away_team:
                print(f"Creating missing away team: '{away_team_name}'")
                away_team = Team(sport_id=1, name=away_team_name, abbreviation=away_team_name[:3].upper())
                self.db.add(away_team)
                self.db.flush() # Get ID
            
            game = None
            if home_team and away_team:
                # Check if game exists
                game = self.db.query(Game).filter(
                    Game.home_team_id == home_team.id,
                    Game.away_team_id == away_team.id
                ).first()
                
                if not game:
                    game = Game(
                        sport_id=1, # Assuming 1 is NFL
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        game_time=item['commence_time'] # Needs parsing if string
                    )
                    self.db.add(game)
                    self.db.flush() # Get ID
            
            if not game:
                continue

            # 2. Save Vegas Lines
            # We'll take the first bookmaker for MVP simplicity
            if not item['bookmakers']:
                continue
                
            bookmaker = item['bookmakers'][0]
            markets = {m['key']: m for m in bookmaker['markets']}
            
            spread = 0.0
            total = 0.0
            
            if 'spreads' in markets:
                # Logic to extract spread for home team
                outcomes = markets['spreads']['outcomes']
                for outcome in outcomes:
                    if outcome['name'] == home_team_name:
                        spread = outcome['point']
                        break
                        
            if 'totals' in markets:
                total = markets['totals']['outcomes'][0]['point']
                
            # Create/Update VegasLine
            vegas_line = self.db.query(VegasLine).filter(VegasLine.game_id == game.id).first()
            if not vegas_line:
                vegas_line = VegasLine(game_id=game.id, source=bookmaker['title'])
                self.db.add(vegas_line)
            
            vegas_line.spread = spread
            vegas_line.total_points = total
            # Implied totals (simple calculation)
            vegas_line.home_implied_total = (total / 2) - (spread / 2)
            vegas_line.away_implied_total = (total / 2) + (spread / 2)
            
            count += 1
            
        self.db.commit()
        self.logger.info(f"Loaded {count} Vegas lines.")
        return count
