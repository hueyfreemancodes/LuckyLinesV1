from ortools.sat.python import cp_model
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class LineupOptimizer:
    """
    High-performance DFS Lineup Optimizer using Google OR-Tools (CP-SAT).
    """
    
    def __init__(self, players: List[Dict[str, Any]], rules: Dict[str, Any]):
        """
        players: List of player dicts with 'id', 'salary', 'points', 'position', 'team'
        rules: Dict with 'salary_cap', 'roster_size', 'positions' (e.g. {'QB': 1, 'RB': 2...})
        """
        self.players = players
        self.rules = rules
        self.model = cp_model.CpModel()
        self.player_vars = {}
        self.solver = cp_model.CpSolver()
        
    def build_model(self):
        """
        Constructs the CP-SAT model variables and constraints.
        """
        # 1. Create variables (0 or 1 for each player)
        for p in self.players:
            self.player_vars[p['id']] = self.model.NewBoolVar(f"player_{p['id']}")
            
        all_vars = list(self.player_vars.values())
        
        # 2. Salary Cap Constraint
        salaries = [p['salary'] for p in self.players]
        self.model.Add(sum(var * salary for var, salary in zip(all_vars, salaries)) <= self.rules['salary_cap'])
        
        # 3. Roster Size Constraint
        self.model.Add(sum(all_vars) == self.rules['roster_size'])
        
        # 4. Position Constraints
        # Group players by position
        pos_vars = {pos: [] for pos in self.rules['positions'].keys()}
        
        # Handle FLEX positions if needed (simplified for MVP: assume strict positions first)
        # In a real app, we'd map players to multiple eligible positions (e.g. RB -> [RB, FLEX])
        
        for p in self.players:
            p_pos = p['position']
            if p_pos in pos_vars:
                pos_vars[p_pos].append(self.player_vars[p['id']])
                
        for pos, count in self.rules['positions'].items():
            if pos == 'FLEX':
                # Special handling for FLEX (RB/WR/TE)
                flex_eligible = []
                for p in self.players:
                    if p['position'] in ['RB', 'WR', 'TE']:
                        flex_eligible.append(self.player_vars[p['id']])
                
                # Total RB+WR+TE = Sum of individual reqs + FLEX count
                total_flex_pool_count = self.rules['positions'].get('RB', 0) + \
                                        self.rules['positions'].get('WR', 0) + \
                                        self.rules['positions'].get('TE', 0) + \
                                        count
                self.model.Add(sum(flex_eligible) == total_flex_pool_count)
            else:
                # Strict position limit (>= to allow for FLEX overlap if not handled explicitly above)
                # For strict implementation:
                self.model.Add(sum(pos_vars[pos]) >= count)

        # 5. Objective: Maximize Projected Points
        projections = [int(p['points'] * 100) for p in self.players] # Convert to int for CP-SAT
        self.model.Maximize(sum(var * proj for var, proj in zip(all_vars, projections)))

    def solve(self, num_lineups: int = 1) -> List[List[Dict[str, Any]]]:
        """
        Generates optimal lineups.
        """
        self.build_model()
        
        # To generate multiple lineups, we solve, add a constraint to forbid the previous solution, and solve again.
        # OR-Tools has a solution callback for this, but iterative solving is simpler for MVP logic.
        
        generated_lineups = []
        
        for _ in range(num_lineups):
            status = self.solver.Solve(self.model)
            
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                lineup = []
                selected_vars = []
                
                for p in self.players:
                    if self.solver.Value(self.player_vars[p['id']]) == 1:
                        lineup.append(p)
                        selected_vars.append(self.player_vars[p['id']])
                
                generated_lineups.append(lineup)
                
                # Add constraint to ban this exact combination in the next iteration
                # sum(selected_vars) <= len(selected_vars) - 1
                self.model.Add(sum(selected_vars) <= len(selected_vars) - 1)
            else:
                break
                
        return generated_lineups
