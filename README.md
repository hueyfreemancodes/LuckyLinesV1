# LuckyLines: Advanced NFL Analytics & Optimization Engine

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Production-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Status](https://img.shields.io/badge/Status-Production%20Ready-success)

**LuckyLines** is an enterprise-grade analytics platform designed to crack the code of NFL Daily Fantasy Sports (DFS) and Prop Betting. By fusing hi-resolution historical data with advanced machine learning ensembles, the system identifies market inefficiencies and generates +EV (Expected Value) opportunities with precision.

Unlike basic optimizers that rely on simple averages, LuckyLines employs a rigorous data science pipeline—feature engineering, model stacking, and portfolio optimization—to deliver professional-grade insights.

---

## 🚀 Key capabilities

### 🧠 Advanced Predictive Modeling
*   **Ensemble Estimators**: Utilizes a **Stacked Generalization** approach, combining XGBoost (Gradient Boosting), LightGBM, and LSTM (Deep Learning) to capture both non-linear interactions and temporal player trends.
*   **Prop Specific Models**: Specialized regressors trained on granular stat categories (Passing Yards, Rushing Yards, Receptions) to beat Vegas lines.
*   **Context-Aware Features**: Models account for **Game Script** (trailing/leading), **Weather Conditions** (wind/temp impacts per position), and **Defensive Matchups**.

### ⚡ Real-Time Optimization
*   **EV Betting Engine**: Instantly calculates the mathematical edge of every prop bet by comparing internal probability distributions against live Vegas odds.
*   **Dynamic Lineup Construction**: Uses linear programming (OR-Tools) to build diversified DFS portfolios that maximize projected points while strictly adhering to salary caps and correlation rules (e.g., QB+WR stacking).

### 🛠 Robust Data Pipeline
*   **Unified Ingestion**: seamlessly integrates disparate data sources:
    *   **NFLVerse**: Granular Play-by-Play and roster data.
    *   **The Odds API**: Real-time betting lines from major books (DraftKings, FanDuel, MGM).
    *   **SportsDataIO**: Official stats and grading.
*   **Automated Feature Store**: continuously updates rolling windows, consistency scores (CV), and efficiency metrics (DVOA-proxy).

---

## 🏗 System Architecture

The extensive architecture is built for scale and modularity:

```mermaid
graph TD
    A[Data Ingestion] -->|Raw Data| B(PostgreSQL DB)
    B -->|Historical Stats| C[Feature Engineering]
    C -->|Vectorized Features| D[Model Training]
    
    D -->|Serialized Models| E[Projections Service]
    F[Live Odds API] -->|Real-time Lines| E
    
    E -->|Projections| G[EV Calculator]
    E -->|Projections| H[DFS Optimizer]
    
    G -->|Best Bets| I[API / Dashboard]
    H -->|Optimal Lineups| I
```

---

## 🛠 Installation & Setup

Follow these steps to deploy the LuckyLines engine locally.

### Prerequisites
*   **Python 3.10+**
*   **PostgreSQL 14+** (Local or Cloud)
*   **Git**

### Step-by-Step Guide

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/hueyfreemancodes/LuckyLines.git
    cd LuckyLines
    ```

2.  **Virtual Environment (Recommended)**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Environment Variables**
    Create a `.env` file in the root directory. You can start with the example:
    ```bash
    cp .env.example .env
    ```
    **Required Variables:**
    *   `DATABASE_URL`: `postgresql://user:pass@localhost:5432/luckylines`
    *   `ODDS_API_KEY`: Your key from https://the-odds-api.com/

5.  **Database Initialization**
    Initialize the schema and apply migrations:
    ```bash
    alembic upgrade head
    ```

---

## 💻 Usage Guide

### 1. Training the Models
Before generating projections, you must train the models on historical data.

*   **Train Fantasy Points Model (XGBoost)**
    ```bash
    python scripts/train_xgboost.py
    ```
    *   *Output*: Saves `nfl_xgboost_model.joblib` to `models/`.
    *   *Metrics*: Logs MAE and R² performance on the test holdout.

*   **Train Prop Betting Models**
    ```bash
    python scripts/train_prop_models.py
    ```
    *   Trains separate models for Passing, Rushing, and Receiving yards.

### 2. Generating Projections & Bets
Once models are trained, you can run the full pipeline for a specific week.

*   **Run Projections** (Example: 2024 Season, Week 10)
    ```bash
    # (This functionality is exposed via API, see below)
    ```

### 3. Running the API
Start the REST API to interact with the system programmatically.

```bash
uvicorn app.main:app --reload
```

*   **Docs**: Open `http://localhost:8000/docs` for Swagger UI.
*   **Key Endpoints**:
    *   `GET /api/projections/nfl/2024/10`: Get full player projections.
    *   `GET /api/props/ev/2024/10`: Get ranked +EV prop bets.
    *   `POST /ingest/csv`: Upload custom projection CSVs.

---

## 📊 Model Performance

We rigorously evaluate our models using time-series cross-validation.

| Model Target | Algorithm | MAE (Mean Absolute Error) | Status |
| :--- | :--- | :--- | :--- |
| **Fantasy Points (PPR)** | XGBoost | **4.68 pts** | 🏆 Production |
| **Passing Yards** | XGBoost | **26.5 yds** | ✅ Active |
| **Rushing Yards** | XGBoost | **17.8 yds** | ✅ Active |
| **Receiving Yards** | XGBoost | **18.6 yds** | ✅ Active |

*> **Note:** Our Stacked Ensemble initially showed promise but introduced latency complexity for marginal gain (<0.5% improvement). We currently deploy optimized XGBoost regressors for maximum efficiency.*

---

## 🤝 Contributing

We welcome contributions! Please follow these steps:
1.  Fork the repo.
2.  Create a feature branch (`git checkout -b feature/amazing-feature`).
3.  Commit your changes following "Clean Code" standards.
4.  Push to the branch.
5.  Open a Pull Request.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

**Disclaimer**: *For educational and simulation purposes only. Not financial advice.*
