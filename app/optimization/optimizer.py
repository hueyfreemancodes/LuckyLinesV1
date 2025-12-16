from ortools.sat.python import cp_model
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class LineupOptimizer:
    """
    High-performance DFS Lineup Optimizer using Google OR-Tools (CP-SAT).
    """
    
    def __init__(self, players: List[Dict[str, Any]], rules: Dict[str, Any], 
                 stacking_rules: Optional[Dict[str, List[str]]] = None,
                 exposure_limits: Optional[Dict[int, float]] = None,
                 min_diversity: int = 0):
        """
        players: List of player dicts with 'id', 'salary', 'points', 'position', 'team'
        rules: Dict with 'salary_cap', 'roster_size', 'positions'
        stacking_rules: Dict mapping position to list of positions to stack with (e.g. {'QB': ['WR', 'TE']})
        exposure_limits: Dict mapping player_id to max fraction of lineups (0.0 to 1.0)
        min_diversity: Min number of players that must differ between lineups
        """
        self.players = players
        self.rules = rules
        self.stacking_rules = stacking_rules or {}
        self.exposure_limits = exposure_limits or {}
        self.min_diversity = min_diversity
        
        self.model = cp_model.CpModel()
        self.player_vars = {}
        self.solver = cp_model.CpSolver()
        # Enable multi-threading for faster solves if needed, though default is usually fine
        # self.solver.parameters.num_search_workers = 4

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
                self.model.Add(sum(pos_vars[pos]) >= count)
                
        # 5. Stacking Constraints
        if self.stacking_rules:
            self.add_stacking_constraints()

        # 6. Objective: Maximize Projected Points
        projections = [int(p['points'] * 100) for p in self.players] # Convert to int for CP-SAT
        self.model.Maximize(sum(var * proj for var, proj in zip(all_vars, projections)))

    def add_stacking_constraints(self):
        """
        Adds constraints to force teammates to be selected with a primary player.
        Example: If QB is selected, at least one WR/TE from same team must be selected.
        """
        for primary_pos, partner_positions in self.stacking_rules.items():
            # Find all players of primary position
            primaries = [p for p in self.players if p['position'] == primary_pos]
            
            for p in primaries:
                # Find eligible partners (same team, correct positions)
                partners = [
                    self.player_vars[teammate['id']] 
                    for teammate in self.players 
                    if teammate['team'] == p['team'] 
                    and teammate['position'] in partner_positions
                    and teammate['id'] != p['id']
                ]
                
                if partners:
                    # Constraint: If Primary is selected (1), Sum(Partners) >= 1
                    # We use OnlyEnforceIf logic
                    self.model.Add(sum(partners) >= 1).OnlyEnforceIf(self.player_vars[p['id']])

    def solve(self, num_lineups: int = 1) -> List[List[Dict[str, Any]]]:
        """
        Generates optimal lineups iteratively.
        """
        self.build_model()
        
        generated_lineups = []
        player_usage_counts = {p['id']: 0 for p in self.players}
        
        for i in range(num_lineups):
            # Apply Exposure Limits (Dynamic Constraints)
            if self.exposure_limits:
                for pid, max_pct in self.exposure_limits.items():
                    current_count = player_usage_counts.get(pid, 0)
                    allowed_count = int(max_pct * num_lineups)
                    
                    if current_count >= allowed_count:
                        # Ban player for this and infinite future lineups in this batch
                        self.model.Add(self.player_vars[pid] == 0)

            status = self.solver.Solve(self.model)
            
            if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
                lineup = []
                selected_vars = []
                
                for p in self.players:
                    if self.solver.Value(self.player_vars[p['id']]) == 1:
                        lineup.append(p)
                        selected_vars.append(self.player_vars[p['id']])
                        player_usage_counts[p['id']] += 1
                
                generated_lineups.append(lineup)
                
                # Diversity Constraint for Next Iteration
                # Force next lineup to have at most (ROSTER_SIZE - min_diversity) overlap
                # i.e. At least `min_diversity` players must be different (not in the currently selected set)
                # But typically diversity means "at least N players different from EACH previous lineup".
                # Standard approach: sum(selected_vars_from_prev) <= RosterSize - MinDiversity
                
                # Add constraint to forbid this exact lineup (Basic)
                # And apply min_diversity if specified
                
                if self.min_diversity > 0:
                     self.model.Add(sum(selected_vars) <= self.rules['roster_size'] - self.min_diversity)
                else:
                    # Basic exclusion
                    self.model.Add(sum(selected_vars) <= self.rules['roster_size'] - 1)
            else:
                logger.info(f"Solver stopped at lineup {i+1}: Status {status}")
                break
                
        return generated_lineups
