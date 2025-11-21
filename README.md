# LuckyLines V1

**Advanced NFL Prop Betting & DFS Analytics Platform**

LuckyLines combines machine learning projections with real-time betting data to identify +EV prop betting opportunities and optimize Daily Fantasy Sports lineups.

---

## 🎯 Features

- **ML-Powered Projections**: XGBoost models for fantasy points, passing yards, rushing yards, and receiving yards
- **Expected Value (EV) Calculator**: Automatically identifies profitable prop bets
- **Injury Integration**: Filters out inactive players to prevent betting on players who won't play
- **Real-Time Odds**: Integration with The Odds API for live prop betting lines
- **Historical Data**: 18,000+ player-game records (2012-2025) from nflverse
- **DFS Optimization**: (Coming Soon) Lineup optimizer with salary constraints

---

## 📊 Model Performance

| Model | Target | MAE | Status |
|:------|:-------|:----|:-------|
| **Fantasy Points** | PPR Points | 4.68 pts | ✅ Production |
| **Passing Yards** | Pass Yds | 26.5 yds | ✅ Production |
| **Rushing Yards** | Rush Yds | 17.8 yds | ✅ Production |
| **Receiving Yards** | Rec Yds | 18.6 yds | ✅ Production |

All models achieve **MAE/StdDev ratios of 0.4-0.5**, significantly outperforming baseline predictions.

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- PostgreSQL 15+

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/LuckyLinesV1.git
   cd LuckyLinesV1
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials and API keys
   ```

3. **Start the database**
   ```bash
   docker-compose up -d db
   ```

4. **Run database migrations**
   ```bash
   docker-compose exec api alembic upgrade head
   ```

5. **Seed the database**
   ```bash
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/seed_db.py"
   ```

6. **Ingest historical data**
   ```bash
   # Sync player rosters
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/sync_rosters_nflverse.py"
   
   # Ingest play-by-play data (this will take a while)
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/ingest_pbp_nflverse.py --start-year 2023 --end-year 2025"
   
   # Ingest Vegas lines
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/ingest_game_lines_nflverse.py"
   
   # Ingest injury data
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/ingest_injuries.py --season 2025"
   ```

7. **Train the models**
   ```bash
   # Train fantasy points model
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/train_xgboost.py"
   
   # Train prop models
   docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/train_prop_models.py"
   ```

---

## 📖 Usage

### Generate Projections

```python
from app.services.projections import ProjectionsService

service = ProjectionsService()
projections = service.generate_projections(season=2025, week=12)

for proj in projections[:5]:
    print(f"{proj['name']}: {proj['points']:.1f} pts, {proj['pass_yds']:.0f} pass yds")
```

### Find +EV Prop Bets

```python
from app.services.ev_calculator import EVService
from app.core.database import SessionLocal

db = SessionLocal()
ev_service = EVService(db)

# Find best bets for Week 12
best_bets = ev_service.find_best_bets(season=2025, week=12, min_ev=0.05)

for bet in best_bets[:10]:
    print(f"{bet['player_name']}: {bet['market']} {bet['line']} ({bet['ev_pct']:.1f}% EV)")
```

### Ingest Live Prop Lines

```python
from app.services.odds_api import OddsAPIService

odds_service = OddsAPIService(api_key="your_api_key")
await odds_service.ingest_player_props()
```

---

## 🗂️ Project Structure

```
LuckyLines/
├── app/
│   ├── api/              # FastAPI endpoints
│   ├── core/             # Database configuration
│   ├── ingestion/        # Data ingestion modules
│   ├── models/           # SQLAlchemy models & ML models
│   ├── optimization/     # DFS lineup optimizer (coming soon)
│   ├── schemas/          # Pydantic schemas
│   └── services/         # Core business logic
│       ├── projections.py          # Projection generation
│       ├── ev_calculator.py        # EV calculation
│       ├── feature_engineering.py  # Feature transformation
│       └── opponent_defense_features.py
├── scripts/              # Data ingestion & training scripts
│   ├── sync_rosters_nflverse.py
│   ├── ingest_pbp_nflverse.py
│   ├── ingest_injuries.py
│   ├── train_xgboost.py
│   └── train_prop_models.py
├── models/               # Trained model files (.joblib)
├── alembic/              # Database migrations
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🧠 How It Works

### 1. Data Ingestion
- **nflverse**: Play-by-play data, rosters, Vegas lines, injury status
- **The Odds API**: Real-time prop betting lines from major sportsbooks

### 2. Feature Engineering
LuckyLines generates 30+ features for each player-game:
- **Time-Series**: EMAs, lags, streaks, velocity
- **Vegas**: Implied team totals, game totals
- **Weather**: Wind, temperature, humidity (position-specific)
- **Opponent Defense**: Rolling 4-game averages for PPG, YPG, sacks, turnovers
- **Player Quality**: VORP, PPG tiers, trends
- **Opportunity**: Red zone share, team share

### 3. ML Models
- **XGBoost Regressors** trained on 18,000+ player-game records
- Separate models for fantasy points, passing yards, rushing yards, receiving yards
- Hyperparameter tuning via grid search

### 4. EV Calculation
For each prop bet:
1. Generate model projection (e.g., 250 passing yards)
2. Calculate win probability using Normal CDF
3. Compute EV = (WinProb × Profit) - (LossProb × Wager)
4. Filter for positive EV bets

### 5. Injury Filtering
- Automatically filters out players with status `INA` (Inactive), `RES` (Reserve), or `CUT`
- Prevents betting on players who won't play

---

## 📈 Data Sources

- **[nflverse](https://github.com/nflverse/nflverse-data)**: Play-by-play, rosters, schedules, Vegas lines
- **[The Odds API](https://the-odds-api.com/)**: Real-time prop betting lines
- **DraftKings API**: DFS salaries and slates (for future lineup optimizer)

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11, FastAPI
- **Database**: PostgreSQL 15
- **ML**: XGBoost, scikit-learn, pandas, numpy
- **Deployment**: Docker, Docker Compose
- **Migrations**: Alembic

---

## 📝 Environment Variables

Create a `.env` file with the following:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/luckylines

# The Odds API
ODDS_API_KEY=your_api_key_here

# Optional: DraftKings API (for DFS optimizer)
DRAFTKINGS_API_KEY=your_dk_api_key
```

---

## 🧪 Testing

Run model evaluation:
```bash
docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/evaluate_all_models.py"
```

---

## 🗺️ Roadmap

- [x] Fantasy points projections
- [x] Prop betting projections (pass/rush/rec yards)
- [x] EV calculator
- [x] Injury integration
- [ ] DFS lineup optimizer
- [ ] Kelly Criterion bet sizing
- [ ] Expand prop markets (TDs, receptions, etc.)
- [ ] Historical prop backtesting
- [ ] Automated daily model retraining

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🙏 Acknowledgments

- **nflverse** for comprehensive NFL data
- **The Odds API** for real-time betting lines
- **XGBoost** team for the excellent ML library

---

## 📧 Contact

For questions or feedback, please open an issue on GitHub.
