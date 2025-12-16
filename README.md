# LuckyLines DFS Backend

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95%2B-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)

A high-performance Daily Fantasy Sports (DFS) backend engine built with **FastAPI** and **PostgreSQL**. This service handles data ingestion, player projections, lineup optimization, and monte-carlo simulations for NFL/NBA DFS contests.

## 🚀 Features

- **Data Ingestion**: Automated pipelines for SportsDataIO, OddsAPI, and CSV data.
- **Projections**: Custom projection models incorporating game script, Vegas lines, and historical performance.
- **Optimization**: Linear programming (OR-Tools) to generate EV-maximizing lineups.
- **EV Betting Analysis**: Script-based engine to identify positive Expected Value (EV) prop bets by comparing internal projections against Vegas lines.
- **Simulation**: Monte-Carlo simulation engine to backtest lineups against thousands of game outcomes.

## 📦 Database Schema

The core PostgreSQL schema is built with SQLAlchemy. Key entities include:

- **Sports & Teams**: Reference tables for leagues (NFL, NBA) and franchises.
- **Players**: Central registry of athletes linked to teams and positions.
- **Games**: Matchup metadata including schedule, weather, and stadium info.
- **PlayerSeasonStats / PlayerGameStats**: Historical performance metrics for modeling.
- **Projections**: Point projections per player per slate.
- **Lineups**: Generated optimal lineups and their projected ROI.

## 🛠️ Setup Guide

### 1. Clone the Repository
```bash
git clone https://github.com/hueyfreemancodes/LuckyLines.git
cd LuckyLines
```

### 2. Configure Environment
Create a `.env` file in the root directory. Use `.env.example` as a template.
```bash
cp .env.example .env
```
**Required Variables:**
- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:pass@localhost:5432/dfs_db`)
- `SPORTSDATAIO_KEY`: API Key for external data (if running ingestion).

### 3. Install Dependencies
It is recommended to use a virtual environment.
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run the Application
Start the API server using Uvicorn.
```bash
uvicorn app.main:app --reload
```
The API will be available at `http://localhost:8000`.

## 🔮 EV Betting Analysis

The compiled proprietary models can be used to scan for value bets.

### Run the Analyzer
```bash
python scripts/run_ev_analysis.py
```
This script will:
1. Load the latest trained models (`models/*.joblib`).
2. Generate projections for the current week.
3. Compare against real-time odds (from DB).
4. Output a list of **+EV Bets** sorted by value.

### Train Models
To retrain the models with the latest data:
```bash
python scripts/train_prop_models.py
```

## 📚 API Documentation

Interactive documentation is available via Swagger UI at:
- **Local**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Core Endpoints
- `GET /api/v1/players`: Retrieve active player pool.
- `POST /api/v1/optimization/optimize`: Generate lineups based on constraints.
- `GET /api/v1/projections/nfl/{season}/{week}`: Fetch specific week projections using the LSTM model.
- `POST /api/v1/training/train`: Trigger background model retraining (NFL only).
