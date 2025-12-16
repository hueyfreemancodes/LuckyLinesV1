import sys
import os
import logging

sys.path.append(os.getcwd())
from app.optimization.optimizer import LineupOptimizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_manual_data():
    """
    Creates a small manual dataset to verify constraints.
    """
    # Create Players (2 Teams: BUF, KC)
    players = [
        # BUF (Stack: Josh Allen + Diggs/Kincaid)
        {"id": 1, "name": "Josh Allen", "position": "QB", "team": "BUF", "salary": 8000, "points": 25.0},
        {"id": 2, "name": "Stefon Diggs", "position": "WR", "team": "BUF", "salary": 7000, "points": 20.0},
        {"id": 3, "name": "Dalton Kincaid", "position": "TE", "team": "BUF", "salary": 5000, "points": 12.0},
        {"id": 4, "name": "James Cook", "position": "RB", "team": "BUF", "salary": 6000, "points": 15.0},
        
        # KC (Stack: Mahomes + Kelce/Rice)
        {"id": 11, "name": "P. Mahomes", "position": "QB", "team": "KC", "salary": 7800, "points": 24.0},
        {"id": 12, "name": "Travis Kelce", "position": "TE", "team": "KC", "salary": 6500, "points": 16.0},
        {"id": 13, "name": "Rashee Rice", "position": "WR", "team": "KC", "salary": 5500, "points": 14.0},
        {"id": 14, "name": "Isiah Pacheco", "position": "RB", "team": "KC", "salary": 5800, "points": 14.5},
        
        # Others (Filler)
        {"id": 20, "name": "Tyreek Hill", "position": "WR", "team": "MIA", "salary": 7500, "points": 22.0},
        {"id": 21, "name": "CMC", "position": "RB", "team": "SF", "salary": 9000, "points": 28.0},
        {"id": 22, "name": "CeeDee Lamb", "position": "WR", "team": "DAL", "salary": 7200, "points": 21.0},
        {"id": 23, "name": "Cheap WR", "position": "WR", "team": "NYG", "salary": 3000, "points": 8.0},
        {"id": 24, "name": "Cheap RB", "position": "RB", "team": "ARI", "salary": 3000, "points": 8.0},
        {"id": 25, "name": "Cheap TE", "position": "TE", "team": "NE", "salary": 3000, "points": 6.0},
        {"id": 26, "name": "Cheap DST", "position": "DST", "team": "DEN", "salary": 3000, "points": 5.0},
    ]
    
    # 1 QB, 1 RB, 1 WR, 1 TE (Simplified rules for testing)
    rules = {
        "salary_cap": 50000,
        "roster_size": 4, 
        "positions": {
            "QB": 1,
            "RB": 1,
            "WR": 1,
            "TE": 1
        }
    }
    
    logger.info("--- Test 1: Stacking (QB + WR/TE) ---")
    stacking = {"QB": ["WR", "TE"]}
    opt = LineupOptimizer(players, rules, stacking_rules=stacking)
    lineups = opt.solve(num_lineups=3)
    
    for i, lineup in enumerate(lineups):
        qb = next(p for p in lineup if p['position'] == 'QB')
        partners = [p for p in lineup if p['team'] == qb['team'] and p['position'] in ['WR', 'TE']]
        logger.info(f"Lineup {i+1}: QB {qb['name']} ({qb['team']}) - Stacked with: {[p['name'] for p in partners]}")
        if not partners:
            logger.error("FAILED: Stacking constraint violated!")
        else:
            logger.info("PASSED")

    logger.info("\n--- Test 2: Exposure Limits (Max 50% Josh Allen) ---")
    # Josh Allen is highest projected QB, so he would be in 100% without limits
    exposure = {1: 0.5} # Josh Allen ID = 1
    # We ask for 4 lineups. Allen should be in max 2.
    opt = LineupOptimizer(players, rules, exposure_limits=exposure)
    lineups = opt.solve(num_lineups=4)
    
    allen_count = sum(1 for l in lineups if any(p['id'] == 1 for p in l))
    logger.info(f"Josh Allen appearing in {allen_count}/4 lineups (Limit: 50% = 2)")
    if allen_count > 2:
        logger.error("FAILED: Exposure limit violated!")
    else:
        logger.info("PASSED")
        
    logger.info("\n--- Test 3: Diversity (Min 2 diff players) ---")
    # Min diversity = 2 means each new lineup must change at least 2 players from previous ones
    opt = LineupOptimizer(players, rules, min_diversity=2)
    lineups = opt.solve(num_lineups=3)
    
    # Check overlap
    for i in range(1, len(lineups)):
        prev = set(p['id'] for p in lineups[i-1])
        curr = set(p['id'] for p in lineups[i])
        overlap = len(prev.intersection(curr))
        diff = 4 - overlap
        logger.info(f"Lineup {i} to {i+1}: Overlap {overlap}, Diff {diff} (Req: >= 2)")
        if diff < 2:
            logger.error("FAILED: Diversity constraint violated!")
        else:
            logger.info("PASSED")

if __name__ == "__main__":
    test_manual_data()
