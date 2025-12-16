from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class PlayerBase(BaseModel):
    id: int
    name: str
    position: str
    salary: int
    team: str
    points: float

class OptimizationRequest(BaseModel):
    sport: str
    salary_cap: int
    roster_size: int
    positions: Dict[str, int]
    num_lineups: int = 1
    players: List[PlayerBase]

class LineupResponse(BaseModel):
    players: List[PlayerBase]
    total_salary: int
    projected_points: float

class SimulationRequest(BaseModel):
    lineups: List[LineupResponse]
    num_iterations: int = 1000

class SimulationResult(BaseModel):
    lineup_index: int
    avg_score: float
    ceiling: float
    floor: float
    win_prob: float
