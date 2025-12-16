from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.schemas import SimulationRequest, SimulationResult
from app.optimization.simulator import Simulator

router = APIRouter()

@router.post("/simulate", response_model=List[SimulationResult])
async def run_simulation(request: SimulationRequest):
    try:
        # Extract unique players from all lineups to build the player pool
        all_players = {}
        lineups_data = []
        
        for lineup in request.lineups:
            lineup_players = []
            for p in lineup.players:
                p_dict = p.dict()
                all_players[p.id] = p_dict
                lineup_players.append(p_dict)
            lineups_data.append(lineup_players)
            
        player_pool = list(all_players.values())
        
        simulator = Simulator(player_pool, num_iterations=request.num_iterations)
        results = simulator.run_simulation(lineups_data)
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
