import numpy as np
from typing import List, Dict, Any

class Simulator:
    """
    Vectorized Monte Carlo Simulation Engine.
    Simulates thousands of slate outcomes to evaluate lineup ROI.
    """
    
    def __init__(self, players: List[Dict[str, Any]], num_iterations: int = 10000):
        self.players = players
        self.num_iterations = num_iterations
        self.player_map = {p['id']: i for i, p in enumerate(players)}
        
    def run_simulation(self, lineups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Runs the simulation for the given lineups.
        Returns the lineups with added simulation metrics (ROI, Win%, etc.)
        """
        num_players = len(self.players)
        
        # 1. Generate outcomes for all players
        # Shape: (num_iterations, num_players)
        # For MVP: Simple normal distribution based on projection & std_dev
        # In production: Use correlated copulas
        
        means = np.array([p['points'] for p in self.players])
        std_devs = np.array([p.get('std_dev', 5.0) for p in self.players]) # Default 5.0 if missing
        
        # Vectorized generation of all player outcomes for all iterations
        # This is the key speedup over looping
        outcomes = np.random.normal(means, std_devs, size=(self.num_iterations, num_players))
        
        # 2. Convert lineups to a boolean matrix
        # Shape: (num_lineups, num_players)
        lineup_matrix = np.zeros((len(lineups), num_players))
        
        for i, lineup in enumerate(lineups):
            for player in lineup:
                idx = self.player_map.get(player['id'])
                if idx is not None:
                    lineup_matrix[i, idx] = 1
                    
        # 3. Calculate lineup scores for every iteration
        # Matrix multiplication: (num_lineups, num_players) @ (num_players, num_iterations) -> (num_lineups, num_iterations)
        # Transpose outcomes to match dimensions
        lineup_scores = lineup_matrix @ outcomes.T
        
        # 4. Analyze results
        # We need to simulate the "field" to calculate ROI.
        # For MVP, we'll just calculate raw score metrics (Cash line proxy)
        
        results = []
        cash_line_proxy = np.percentile(lineup_scores, 50, axis=0) # Median score of OUR lineups as a baseline
        
        for i, lineup in enumerate(lineups):
            scores = lineup_scores[i]
            
            avg_score = np.mean(scores)
            ceiling = np.percentile(scores, 95)
            floor = np.percentile(scores, 5)
            win_prob = np.mean(scores > 150) # Arbitrary 150pt threshold for MVP
            
            results.append({
                "lineup_index": i,
                "avg_score": float(avg_score),
                "ceiling": float(ceiling),
                "floor": float(floor),
                "win_prob": float(win_prob)
            })
            
        return results
