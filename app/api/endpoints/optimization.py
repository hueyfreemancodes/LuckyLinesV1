from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.schemas import OptimizationRequest, LineupResponse
from app.optimization.optimizer import LineupOptimizer

router = APIRouter()

@router.post("/optimize", response_model=List[LineupResponse])
async def optimize_lineups(request: OptimizationRequest):
    try:
        # Convert Pydantic models to dicts for the optimizer
        players_data = [p.dict() for p in request.players]
        rules = {
            "salary_cap": request.salary_cap,
            "roster_size": request.roster_size,
            "positions": request.positions
        }
        
        optimizer = LineupOptimizer(players_data, rules)
        generated_lineups = optimizer.solve(num_lineups=request.num_lineups)
        
        response = []
        for lineup in generated_lineups:
            total_salary = sum(p['salary'] for p in lineup)
            total_points = sum(p['points'] for p in lineup)
            
            response.append(LineupResponse(
                players=lineup,
                total_salary=total_salary,
                projected_points=total_points
            ))
            
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto", response_model=List[LineupResponse])
async def auto_optimize(
    season: int, 
    week: int, 
    salary_cap: int = 50000,
    num_lineups: int = 1
):
    """
    End-to-End Optimization:
    1. Fetch Data & Generate Projections (LSTM)
    2. Optimize Lineups
    """
    from app.services.projections import ProjectionsService
    
    try:
        # 1. Get Projections
        service = ProjectionsService()
        projections = service.generate_projections(season, week)
        
        if not projections:
            raise HTTPException(status_code=404, detail="No projections available to optimize.")
            
        # 2. Prepare for Optimizer
        # Map projection format to optimizer format
        players_data = []
        for p in projections:
            players_data.append({
                "id": p['id'],
                "name": p['name'],
                "position": p['position'],
                "team": p['team'],
                "salary": p['salary'],
                "points": p['points']
            })
            
        # Default NFL Rules (DraftKings Classic approx)
        rules = {
            "salary_cap": salary_cap,
            "roster_size": 9,
            "positions": {
                "QB": 1,
                "RB": 2,
                "WR": 3,
                "TE": 1,
                "DST": 1,
                "FLEX": 1
            }
        }
        
        # 3. Optimize
        optimizer = LineupOptimizer(players_data, rules)
        generated_lineups = optimizer.solve(num_lineups=num_lineups)
        
        response = []
        for lineup in generated_lineups:
            total_salary = sum(p['salary'] for p in lineup)
            total_points = sum(p['points'] for p in lineup)
            
            # Map back to PlayerBase schema
            # Note: LineupOptimizer returns dicts, schema expects objects if we strictly follow Pydantic
            # But Pydantic can handle dicts usually.
            
            response.append(LineupResponse(
                players=lineup,
                total_salary=total_salary,
                projected_points=total_points
            ))
            
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
