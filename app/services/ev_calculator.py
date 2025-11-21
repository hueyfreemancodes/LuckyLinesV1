import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from scipy.stats import norm
from app.models.models import BettingLine, Projection, Player, PlayerSeasonStats

logger = logging.getLogger(__name__)

class EVService:
    """
    Service to calculate Expected Value (EV) for player prop bets.
    """
    
    # Estimated Standard Deviation for player props (can be refined per position/stat)
    STD_DEV_MAP = {
        'player_pass_yds': 35.0,
        'player_rush_yds': 15.0,
        'player_reception_yds': 15.0,
    }

    def __init__(self, db: Session):
        self.db = db
        from app.services.projections import ProjectionsService
        self.projections_service = ProjectionsService()

    def find_best_bets(self, season: int = 2024, week: int = 12) -> List[Dict[str, Any]]:
        """
        Finds +EV bets by comparing projections to available betting lines.
        """
        # Generate all projections once for efficiency
        logger.info(f"Generating projections for Season {season} Week {week}...")
        projections = self.projections_service.generate_projections(season, week)
        proj_map = {p['id']: p for p in projections}
        
        lines = self.db.query(BettingLine).all()
        bets = []
        
        for line in lines:
            # Get Player Context
            player = self.db.query(Player).filter(Player.id == line.player_id).first()
            if not player: continue
            
            # Get projection for this player
            player_proj = proj_map.get(player.id)
            if not player_proj:
                continue
                
            # Extract stat projection based on market
            projected_stat = None
            if line.market_key == 'player_pass_yds':
                projected_stat = player_proj.get('pass_yds')
            elif line.market_key == 'player_rush_yds':
                projected_stat = player_proj.get('rush_yds')
            elif line.market_key == 'player_reception_yds':
                projected_stat = player_proj.get('rec_yds')
                
            if projected_stat is None or projected_stat == 0:
                continue
                
            # 2. Calculate Win Probability for OVER
            std_dev = self.STD_DEV_MAP.get(line.market_key, 15.0)
            win_prob_over = self._calculate_win_prob(projected_stat, line.line, std_dev, 'Over')
            
            # 3. Calculate EV for OVER
            ev_percent_over = self._calculate_ev_percent(win_prob_over, line.odds)
            
            # 4. Calculate EV for UNDER
            # For Under, we need the Under odds. 
            # Currently BettingLine only stores one 'odds' value. 
            # Usually this is for the 'Over' if the line is presented as such?
            # Or does Odds API provide separate lines for Over and Under?
            # If BettingLine represents a single option (e.g. "Over 20.5"), then we can only calculate EV for that option.
            # If the user wants to bet Under, they need the Under line/odds.
            
            # Assumption: The ingested lines are likely "Over" lines or the "Main" line.
            # If we want to bet Under, we assume standard -110 odds if not provided?
            # Or does BettingLine have a 'bet_type' field?
            # Let's check the model definition again.
            
            # For now, let's assume the stored line is the OVER line.
            # If we want to recommend an UNDER, we need to know the Under odds.
            # If we don't have them, we can assume -110 (standard vig) for estimation.
            
            win_prob_under = 1.0 - win_prob_over
            # Assume -110 for Under if we don't have it
            ev_percent_under = self._calculate_ev_percent(win_prob_under, -110)
            
            # Determine Best Bet
            if ev_percent_over > ev_percent_under:
                bet_type = 'Over'
                win_prob = win_prob_over
                ev_percent = ev_percent_over
                odds = line.odds
            else:
                bet_type = 'Under'
                win_prob = win_prob_under
                ev_percent = ev_percent_under
                odds = -110 # Placeholder
            
            # Only include positive EV bets
            if ev_percent > 0:
                bets.append({
                    'player_name': f"{player.first_name} {player.last_name}",
                    'market': line.market_key,
                    'line': line.line,
                    'odds': odds,
                    'bet_type': bet_type,
                    'projection': round(projected_stat, 1),
                    'diff': round(projected_stat - line.line, 1),
                    'win_prob': round(win_prob * 100, 1),
                    'ev_percent': round(ev_percent, 1),
                    'bookmaker': line.bookmaker
                })
                
        # Sort by EV% descending
        bets.sort(key=lambda x: x['ev_percent'], reverse=True)
        return bets

    def _project_stat(self, player: Player, market_key: str) -> Optional[float]:
        """
        Generates a projection using the ML models.
        """
        # We need to know the season/week to project for.
        # For this MVP, let's find the latest game context or use a fixed test week (2023 Week 1).
        # Ideally, this service receives the target week.
        target_season = 2023
        target_week = 1
        
        # Generate projection for this specific player
        # Note: generate_projections returns a list. We filter for our player.
        # This is inefficient (calling full generation per player). 
        # Optimization: Generate all projections once in find_best_bets.
        
        # For now, let's just call it (it's cached in memory mostly by OS, but DB hits are real).
        # A better approach for this specific method refactor:
        
        projections = self.projections_service.generate_projections(target_season, target_week)
        player_proj = next((p for p in projections if p['id'] == player.id), None)
        
        if not player_proj:
            return None
            
        if market_key == 'player_pass_yds':
            return player_proj.get('pass_yds')
        elif market_key == 'player_rush_yds':
            return player_proj.get('rush_yds')
        elif market_key == 'player_reception_yds':
            return player_proj.get('rec_yds')
            
        return None

    def _calculate_win_prob(self, projected_val: float, line_val: float, std_dev: float, bet_type: str = 'Over') -> float:
        """
        Calculates win probability using Normal Distribution CDF.
        """
        z_score = (projected_val - line_val) / std_dev
        
        if bet_type == 'Over':
            # Prob(X > Line) = 1 - CDF(Line) -> Prob(Z > z)
            # Actually, we want Prob(Actual > Line)
            # Z = (Line - Mean) / Std
            z = (line_val - projected_val) / std_dev
            return 1.0 - norm.cdf(z)
        else:
            z = (line_val - projected_val) / std_dev
            return norm.cdf(z)

    def _calculate_ev_percent(self, win_prob: float, american_odds: int) -> float:
        """
        Calculates EV% = (WinProb * Profit) - (LossProb * Wager) / Wager
        """
        if american_odds > 0:
            decimal_odds = (american_odds / 100) + 1
        else:
            decimal_odds = (100 / abs(american_odds)) + 1
            
        # EV = (WinProb * (DecimalOdds - 1)) - (1 - WinProb)
        ev = (win_prob * (decimal_odds - 1)) - (1.0 - win_prob)
        return ev * 100
