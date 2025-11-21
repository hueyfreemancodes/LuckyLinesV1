# LuckyLines - NFL DFS & Prop Betting Platform

## Project Overview
LuckyLines is an advanced NFL analytics platform that combines machine learning projections with real-time betting data to optimize Daily Fantasy Sports (DFS) lineups and identify +EV prop betting opportunities.

---

## Database Schema

### Core Tables

#### **Players & Teams**
- **`players`**: NFL player roster (name, position, team, external IDs for DFS platforms)
- **`teams`**: NFL teams (name, abbreviation, sport)
- **`sports`**: Sport definitions (currently NFL)

#### **Games & Context**
- **`games`**: NFL games with weather and stadium data
  - Season, week, home/away teams
  - Weather: wind speed, temperature (high/low), humidity, description
  - Stadium details (JSON)

#### **Historical Performance**
- **`player_game_stats`**: Per-game player statistics (2012-2025)
  - Passing: yards, TDs, completions, attempts, interceptions
  - Rushing: yards, TDs, attempts
  - Receiving: yards, TDs, receptions, targets
  - Red zone: targets, attempts (pass/rush)
  - Fantasy points (Half PPR, Full PPR calculated)
  - **Injury Status:** `status` column (ACT, INA, RES) for filtering inactive players
  - **~18,000+ records** with valid game linkage

- **`player_season_stats`**: Season-level aggregates
  - VORP (Value Over Replacement Player)
  - PPG (Points Per Game)
  - Total yards, TDs, games played/started
  - Age, position

#### **Team Performance**
- **`team_game_offense_stats`**: Team offensive stats per game
  - Total yards, pass/rush attempts, pass/rush yards
  - Used for calculating player opportunity shares

- **`team_game_defense_stats`**: Team defensive stats per game
  - Points allowed, yards allowed
  - Sacks, interceptions, fumbles recovered
  - Used for opponent defense features

#### **Vegas Lines**
- **`vegas_lines`**: Historical game lines (2012-2023)
  - Total points (over/under)
  - Spread
  - Implied totals (home/away)
  - **~805 records** from historical data

#### **Betting & DFS**
- **`betting_lines`**: Real-time player prop lines
  - Market (pass_yds, rush_yds, reception_yds, etc.)
  - Line value, odds (American format)
  - Bookmaker, timestamp

- **`slates`**: DFS contest slates (DraftKings, FanDuel)
- **`player_slates`**: Player salaries and availability per slate

- **`projections`**: Model-generated projections (cached)

---

## Data Sources

### Historical Data (CSV Ingestion)
1. **`spreadspoke_scores.csv`** (10,760 games, 2012-2023)
   - Game results, weather, Vegas lines
   - Source: Spreadspoke (Kaggle)

2. **`fantasy_data (1).csv`** (Player season stats)
   - VORP, PPG, raw stats (2012-2023)
   - Source: FantasyPros/Custom aggregation

3. **`nfl_pbp.csv`** (Play-by-play data)
   - Granular play data (optional, not yet fully integrated)

### Live Data (API Integration)
1. **The Odds API** (`odds_api.py`)
   - Real-time player props (pass_yds, rush_yds, rec_yds, TDs, etc.)
   - Multiple bookmakers (DraftKings, FanDuel, BetMGM, etc.)
   - Fetches markets for upcoming games

2. **DFS Platforms** (Future: RotoGrinders, FantasyPros)
   - Player salaries, ownership projections
   - Currently manual CSV upload

---

## Machine Learning Models

### 1. **Fantasy Points Model** (Primary DFS Model)
**File:** `nfl_xgboost_model.joblib`  
**Target:** `fantasy_points_ppr`  
**Algorithm:** XGBoost Regressor  
**Performance:** MAE 4.68 points  
**Status:** ✅ Production (Winner among 4 models tested)

### 2. **Passing Yards Model** (Prop Betting)
**File:** `passing_yards_model.joblib`  
**Target:** `passing_yards`  
**Algorithm:** XGBoost Regressor  
**Positions:** QB only  
**Performance:** MAE 26.5 yards  
**Status:** ✅ Trained, Ready for Production

### 3. **Rushing Yards Model** (Prop Betting)
**File:** `rushing_yards_model.joblib`  
**Target:** `rushing_yards`  
**Algorithm:** XGBoost Regressor  
**Positions:** RB, QB  
**Performance:** MAE 17.8 yards  
**Status:** ✅ Trained, Ready for Production

### 4. **Receiving Yards Model** (Prop Betting)
**File:** `receiving_yards_model.joblib`  
**Target:** `receiving_yards`  
**Algorithm:** XGBoost Regressor  
**Positions:** WR, TE, RB  
**Performance:** MAE 18.6 yards  
**Status:** ✅ Trained, Ready for Production

### Alternative Models (Evaluated but Not Selected)
- **LSTM Model:** Sequence-based, handles time-series
- **Position-Based Model:** Separate XGBoost per position
- **Stacked Ensemble:** Combines multiple models
- **Result:** XGBoost (single model) outperformed all alternatives

---

## Model Features

### Time-Series Features
- **EMAs (Exponential Moving Averages):** 4-game span
  - Fantasy points, targets, rush attempts, red zone share, opportunity share
- **Lags:** 1-game lag for fantasy points, targets, rush attempts
- **Streaks:** Consecutive games over 15 points
- **Velocity:** Rate of change in fantasy points

### Vegas Market Features
- **`implied_team_total`**: Team's expected score (from spread + total)
- **`vegas_total`**: Game total (over/under)
- **Impact:** ~2% feature importance, helps model adjust for game script

### Weather Features (Position-Specific)
- **`weather_wind_passing_penalty`**: Wind impact on passing (QB/WR/TE)
- **`weather_wind_rushing_boost`**: Wind benefit for rushing (RB)
- **`weather_temp_extreme`**: Extreme temperature flag (<32°F or >90°F)
- **`weather_high_humidity`**: Humidity >70%

### Opponent Defense Features
- **`opp_def_ppg_allowed`**: Points allowed (4-game rolling avg)
- **`opp_def_ypg_allowed`**: Yards allowed (4-game rolling avg)
- **`opp_def_sacks_per_game`**: Sacks per game
- **`opp_def_turnovers_per_game`**: Turnovers forced per game
- **`opp_def_strength_score`**: Composite defensive rating

### Player Quality Features
- **`vorp_last_season`**: VORP from previous season
- **`ppg_last_season`**: PPG from previous season
- **`ppg_last_season_squared`**: Non-linear PPG effect
- **`player_ppg_trend`**: Current vs. previous season PPG
- **`vorp_tier`**: Categorical VORP bucket
- **`ppg_tier`**: Categorical PPG bucket

### Opportunity Features
- **`red_zone_share`**: % of team's red zone opportunities
- **`opportunity_share`**: % of team's total opportunities (targets + rush attempts)
- **`team_pass_attempts`**: Team's passing volume
- **`team_rush_attempts`**: Team's rushing volume

---

## Model Performance Summary

| Model | Target | MAE | Std Dev | MAE/Std | Status |
|:------|:-------|:----|:--------|:--------|:-------|
| **Fantasy Points** | `fantasy_points_ppr` | 4.68 | ~12.0 | 0.39 | ✅ Production |
| **Passing Yards** | `passing_yards` | 26.5 | ~50.0 | 0.53 | ✅ Ready |
| **Rushing Yards** | `rushing_yards` | 17.8 | 33.6 | 0.53 | ✅ Ready |
| **Receiving Yards** | `receiving_yards` | 18.6 | ~35.0 | 0.53 | ✅ Ready |

**Interpretation:**  
- MAE/Std ratio of **0.4-0.5 is excellent** for sports prediction
- Models predict within **~0.5 standard deviations** on average
- Significantly better than baseline (season averages)

---

## Core Services

### 1. **ProjectionsService** (`app/services/projections.py`)
**Purpose:** Generate player projections for a given week  
**Inputs:** Season, week  
**Outputs:** List of projections with:
- Fantasy points (`points`)
- Passing yards (`pass_yds`)
- Rushing yards (`rush_yds`)
- Receiving yards (`rec_yds`)
- Player metadata (name, position, team, salary)

**Process:**
1. Fetch historical player stats (6-week lookback for EMAs)
2. Fetch game context (weather, Vegas lines, opponent)
3. Fetch team stats (for opportunity shares)
4. Calculate all features via `FeatureEngineering`
5. Run 4 models (fantasy + 3 prop models)
6. Return comprehensive projections

### 2. **FeatureEngineering** (`app/services/feature_engineering.py`)
**Purpose:** Transform raw data into model features  
**Methods:**
- `calculate_exponential_moving_averages()`: EMAs
- `calculate_lag_features()`: Lag values
- `calculate_streak_coefficient()`: Hot/cold streaks
- `calculate_velocity()`: Trend direction
- `calculate_implied_totals()`: Vegas-based team totals
- `calculate_weather_features()`: Position-specific weather impact
- `calculate_fantasy_context_features()`: VORP/PPG tiers
- `calculate_opponent_defense_features()`: Defensive matchup quality
- `calculate_team_shares()`: Opportunity shares
- `calculate_red_zone_share()`: Red zone usage

### 3. **EVService** (`app/services/ev_calculator.py`)
**Purpose:** Calculate Expected Value for prop bets  
**Inputs:** Season, week (for projections), betting lines from DB  
**Outputs:** List of +EV bets sorted by EV%

**Process:**
1. Generate all projections (batch)
2. Fetch all betting lines from DB
3. For each line:
   - Extract model projection for that stat
   - Calculate win probability (Normal CDF)
   - Calculate EV% = (WinProb × Profit) - (LossProb × Wager)
4. Sort by EV% descending

**Performance:** Optimized to ~5 seconds for 218 bets

### 4. **OddsAPIService** (`app/services/odds_api.py`)
**Purpose:** Fetch real-time prop lines from The Odds API  
**Markets:** `player_pass_yds`, `player_rush_yds`, `player_reception_yds`, `player_pass_tds`, etc.  
**Bookmakers:** DraftKings, FanDuel, BetMGM, Caesars, etc.

**Process:**
1. Fetch props for upcoming NFL games
2. Parse JSON response
3. Map player names to DB (fuzzy matching)
4. Store in `betting_lines` table

### 5. **OpponentDefenseFeatures** (`app/services/opponent_defense_features.py`)
**Purpose:** Calculate rolling defensive stats for matchup analysis  
**Features:** 4-game rolling averages for PPG allowed, YPG allowed, sacks, turnovers

---

## Key Scripts

### Training Scripts
- **`train_xgboost.py`**: Train fantasy points model
- **`train_prop_models.py`**: Train all 3 prop models (pass/rush/rec yards)
- **`evaluate_all_models.py`**: Compare XGBoost, LSTM, Position, Stacked models

### Ingestion Scripts (Essential)
- **`sync_rosters_nflverse.py`**: Sync player rosters from nflverse
- **`ingest_pbp_nflverse.py`**: Ingest play-by-play data from nflverse
- **`ingest_game_lines_nflverse.py`**: Ingest historical Vegas lines from nflverse
- **`ingest_weekly_stats_nflverse.py`**: Ingest weekly player stats from nflverse
- **`ingest_defensive_stats.py`**: Ingest team defense stats
- **`ingest_injuries.py`**: Ingest player availability status (ACT/INA/RES) from nflverse
- **`backfill_game_ids.py`**: Link player stats to games (critical for features)
- **`seed_db.py`**: Initial database setup



---

## Tomorrow's Next Steps

### 🔍 **1. Investigate Betting Lines Data**
**Goal:** Understand why betting lines seem unrealistic

**Tasks:**
- [ ] Query `betting_lines` table to inspect data
  ```sql
  SELECT * FROM betting_lines LIMIT 20;
  ```
- [ ] Check `bookmaker`, `market_key`, `created_at` columns
- [ ] Verify if these are test data, alternate lines, or real main lines
- [ ] Compare to fresh lines from The Odds API

**Hypothesis:** Lines in DB are likely:
- Alternate lines (not main market)
- Test/seed data
- Stale/corrupted data

### 🚀 **2. Build Prop Betting API Endpoints**
**Goal:** Expose prop projections and EV calculations via REST API

**Endpoints to Create:**
- `GET /api/projections/{season}/{week}` - Get all projections (fantasy + props)
- `GET /api/props/ev/{season}/{week}` - Get +EV prop bets
- `GET /api/props/lines` - Get current betting lines
- `POST /api/props/lines/refresh` - Fetch fresh lines from Odds API

### 🧹 **3. Codebase Cleanup** (Completed Tonight)
**Goal:** Remove diagnostic/one-off scripts, keep only essential code

**Categories to Remove:**
- Diagnostic scripts (`check_*`, `debug_*`, `diagnose_*`, `verify_*`)
- One-time backfill scripts (already run)
- Test scripts for deprecated features
- Duplicate/obsolete model files

**Keep:**
- Core services (`projections.py`, `ev_calculator.py`, `feature_engineering.py`, etc.)
- Training scripts (`train_xgboost.py`, `train_prop_models.py`)
- Essential ingestion scripts
- API endpoints
- Active models (XGBoost for fantasy + 3 prop models)

### 📊 **4. Model Deployment Decision**
**Question:** Deploy prop models to production?

**Considerations:**
- Prop models are trained and performing well (MAE 17-26 yards)
- Need to verify betting lines are realistic first
- May want to backtest on historical props before going live

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     LuckyLines Platform                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Data Sources                                                │
│  ├── Historical CSVs (spreadspoke, fantasy_data)            │
│  ├── The Odds API (real-time props)                         │
│  └── DFS Platforms (salaries, slates)                       │
│                                                               │
│  Database (PostgreSQL)                                       │
│  ├── Players, Teams, Games                                  │
│  ├── PlayerGameStats (14k records)                          │
│  ├── PlayerSeasonStats (VORP, PPG)                          │
│  ├── TeamGameDefenseStats                                   │
│  ├── VegasLines (805 records)                               │
│  └── BettingLines (real-time props)                         │
│                                                               │
│  Feature Engineering                                         │
│  ├── Time-Series (EMAs, Lags, Streaks, Velocity)           │
│  ├── Vegas (Implied Totals, Game Total)                    │
│  ├── Weather (Wind, Temp, Humidity - Position-Specific)    │
│  ├── Opponent Defense (PPG, YPG, Sacks, Turnovers)         │
│  ├── Player Quality (VORP, PPG Tiers, Trends)              │
│  └── Opportunity (Red Zone Share, Team Share)              │
│                                                               │
│  ML Models (XGBoost)                                         │
│  ├── Fantasy Points (MAE 4.68) ✅ Production                │
│  ├── Passing Yards (MAE 26.5) ✅ Ready                      │
│  ├── Rushing Yards (MAE 17.8) ✅ Ready                      │
│  └── Receiving Yards (MAE 18.6) ✅ Ready                    │
│                                                               │
│  Services                                                    │
│  ├── ProjectionsService (generate all projections)          │
│  ├── EVService (calculate +EV bets)                         │
│  ├── OddsAPIService (fetch real-time lines)                 │
│  └── FeatureEngineering (transform raw data)                │
│                                                               │
│  API (FastAPI) - TODO: Add prop endpoints                   │
│  ├── /api/players                                           │
│  ├── /api/projections (fantasy only currently)              │
│  └── /api/props/* (TO BE BUILT)                             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Current Status

### ✅ **Completed**
- Historical data ingestion (10,760 games, 14k player-game records)
- 4 ML models trained (1 fantasy, 3 props)
- Feature engineering pipeline (30+ features)
- Vegas lines integration (historical)
- Odds API integration (real-time)
- EV calculation service
- Batch projection optimization

### 🚧 **In Progress**
- Prop betting API endpoints
- Betting lines validation

### 📋 **Backlog**
- Automated daily model retraining
- Kelly Criterion bet sizing
- Expand prop markets (TDs, receptions, etc.)
- DFS lineup optimizer integration
- Historical prop backtesting
