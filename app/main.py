from fastapi import FastAPI
from app.api.endpoints import optimization, simulation, players, ingestion, training, projections

app = FastAPI(title="LuckyLines API")

app.include_router(optimization.router, prefix="/api/v1", tags=["optimization"])
app.include_router(simulation.router, prefix="/api/v1", tags=["simulation"])
app.include_router(players.router, prefix="/api/v1", tags=["players"])
app.include_router(ingestion.router, prefix="/api/v1", tags=["ingestion"])
app.include_router(training.router, prefix="/api/v1", tags=["training"])
app.include_router(projections.router, prefix="/api/v1", tags=["projections"])

@app.get("/")
async def root():
    return {"message": "DFS Backend is running"}
