import requests
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.models import BettingLine, Player, Game, Team

logger = logging.getLogger(__name__)

class OddsAPIService:
    """
    Service to interact with The Odds API and ingest player props.
    """
    BASE_URL = "https://api.the-odds-api.com/v4/sports"
    
    def __init__(self, db: Session):
        self.db = db
        self.api_key = os.getenv("ODDS_API_KEY")
        if not self.api_key:
            logger.warning("ODDS_API_KEY not found in environment variables.")

    def fetch_player_props(self, sport: str = "americanfootball_nfl", markets: str = "player_pass_yds,player_rush_yds,player_reception_yds,player_anytime_td") -> int:
        """
        Fetches player props for upcoming games and saves them to the database.
        Returns the number of lines processed.
        """
        if not self.api_key:
            return 0
            
        try:
            # 1. Get upcoming events (games)
            events_url = f"{self.BASE_URL}/{sport}/events"
            params = {
                "apiKey": self.api_key,
                "regions": "us",
                "oddsFormat": "american",
                "dateFormat": "iso",
            }
            
            response = requests.get(events_url, params=params)
            response.raise_for_status()
            events = response.json()
            
            if not events:
                logger.info("No upcoming games found.")
                return 0
                
            total_lines_saved = 0
            
            # 2. Iterate through events and fetch props
            for event in events:
                api_game_id = event['id']
                home_team_name = event['home_team']
                away_team_name = event['away_team']
                game_time = event.get('commence_time')
                
                logger.info(f"Fetching props for {away_team_name} @ {home_team_name}...")
                
                # Find or create Game record
                db_game = self._find_or_create_game(home_team_name, away_team_name, game_time)
                if not db_game:
                    logger.warning(f"Could not create/find game for {away_team_name} @ {home_team_name}")
                    continue
                
                props_url = f"{self.BASE_URL}/{sport}/events/{api_game_id}/odds"
                props_params = {
                    "apiKey": self.api_key,
                    "regions": "us",
                    "markets": markets,
                    "oddsFormat": "american",
                    "dateFormat": "iso",
                }
                
                props_response = requests.get(props_url, params=props_params)
                
                if props_response.status_code == 401:
                    logger.error("Unauthorized: Check API Key.")
                    break
                if props_response.status_code == 429:
                    logger.warning("Rate limit exceeded.")
                    break
                    
                props_response.raise_for_status()
                props_data = props_response.json()
                
                lines_saved = self.process_odds(props_data, db_game.id)
                total_lines_saved += lines_saved
                
            return total_lines_saved
            
        except Exception as e:
            logger.error(f"Error fetching player props: {e}")
            return 0

    def process_odds(self, data: Dict[str, Any], game_id: int) -> int:
        """
        Parses the JSON response from The Odds API and saves BettingLines.
        Now includes game_id to link props to specific games.
        """
        lines_count = 0
        bookmakers = data.get('bookmakers', [])
        
        target_books = ['DraftKings', 'FanDuel', 'BetMGM']
        
        for bookmaker in bookmakers:
            book_title = bookmaker['title']
            if book_title not in target_books:
                continue
                
            for market in bookmaker['markets']:
                market_key = market['key']
                
                for outcome in market['outcomes']:
                    player_name = outcome['description']
                    side = outcome['name'] # Over/Under/Yes
                    
                    point = outcome.get('point')
                    price = outcome.get('price')
                    
                    if point is None and 'td' not in market_key:
                        continue # Need a line for yards props
                        
                    # Find Player in DB
                    player = self._find_player(player_name)
                    if not player:
                        logger.debug(f"Player not found: {player_name}")
                        continue
                        
                    # Calculate Implied Probability
                    implied_prob = self._calculate_implied_prob(price)
                    
                    # Create/Update BettingLine (store both Over and Under)
                    line = self.db.query(BettingLine).filter(
                        BettingLine.player_id == player.id,
                        BettingLine.game_id == game_id,
                        BettingLine.bookmaker == book_title,
                        BettingLine.market_key == market_key,
                        BettingLine.side == side
                    ).first()
                        
                    if not line:
                        line = BettingLine(
                            player_id=player.id,
                            game_id=game_id,
                            bookmaker=book_title,
                            market_key=market_key,
                            side=side
                        )
                        self.db.add(line)
                    
                    line.line = point
                    line.odds = price
                    line.implied_prob = implied_prob
                    
                    lines_count += 1
        
        self.db.commit()
        return lines_count

    def _find_player(self, name: str) -> Optional[Player]:
        """
        Fuzzy match player name to database.
        """
        # 1. Exact Match
        parts = name.split()
        if len(parts) < 2: return None
        
        first = parts[0]
        last = " ".join(parts[1:])
        
        player = self.db.query(Player).filter(
            Player.first_name.ilike(first),
            Player.last_name.ilike(last)
        ).first()
        
        if player: return player
        
        # 2. Simple fuzzy (First Initial + Last)
        # "J. Allen" -> "Josh Allen"
        if len(first) == 2 and first[1] == '.':
             player = self.db.query(Player).filter(
                Player.first_name.startswith(first[0]),
                Player.last_name.ilike(last)
            ).first()
             
        return player

    def _calculate_implied_prob(self, american_odds: int) -> float:
        """
        Converts American odds to implied probability.
        """
        if american_odds > 0:
            return 100 / (american_odds + 100)
        else:
            return abs(american_odds) / (abs(american_odds) + 100)
    
    def _find_or_create_game(self, home_team_name: str, away_team_name: str, game_time_str: str) -> Optional[Game]:
        """
        Finds or creates a Game record for the given teams and time.
        """
        # Parse game time
        try:
            game_time = datetime.fromisoformat(game_time_str.replace('Z', '+00:00'))
        except:
            logger.warning(f"Could not parse game time: {game_time_str}")
            game_time = None
        
        # Find teams in DB
        home_team = self.db.query(Team).filter(Team.name.ilike(f"%{home_team_name}%")).first()
        away_team = self.db.query(Team).filter(Team.name.ilike(f"%{away_team_name}%")).first()
        
        if not home_team or not away_team:
            logger.warning(f"Teams not found in DB: {home_team_name}, {away_team_name}")
            return None
        
        # Check if game already exists
        game = self.db.query(Game).filter(
            Game.home_team_id == home_team.id,
            Game.away_team_id == away_team.id,
            Game.game_time == game_time
        ).first()
        
        if not game:
            # Create new game
            game = Game(
                sport_id=1,  # Assuming NFL is sport_id=1
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                game_time=game_time
            )
            self.db.add(game)
            self.db.commit()
            logger.info(f"Created new game: {away_team_name} @ {home_team_name}")
        
        return game
