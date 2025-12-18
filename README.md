# LuckyLines: Advanced DFS Optimization Pipeline

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95%2B-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-orange)

LuckyLines is an enterprise-grade Daily Fantasy Sports (DFS) and prop betting optimization engine. It automates the entire lifecycle of DFS strategy—from raw data ingestion to generating Expected Value (EV) positive lineups and prop bets. The system leverages machine learning ensembles (XGBoost, LSTM, CatBoost) to project player performance and uses linear programming for lineup construction.

## 🏗 System Architecture

The pipeline consists of four main stages:

1.  **Data Ingestion Layer**:
    *   **Sources**: SportsDataIO, NFLVerse, OddsAPI, and custom CSV feeds.
    *   **normalization**: Standardizes player names, team abbreviations, and game metadata across different providers.
    *   **Storage**: Relational data warehousing in PostgreSQL.

2.  **Feature Engineering Service**:
    *   Calculates advanced metrics such as DVOA-adjusted efficiency, Game Script interaction terms, and Velocity of production (short-term vs. long-term trends).
    *   Derives situational features like Weather Impact and Roster Context.

3.  **Predictive Modeling Core**:
    *   **Stacked Ensemble**: Combines predictions from multiple weak learners (XGBoost, LightGBM) and a sequence model (LSTM) using a meta-learner.
    *   **Prop Models**: Specialized regression models for specific stat categories (Passing Yards, Rushing Yards, Receptions).

4.  **Optimization Engine**:
    *   Uses **OR-Tools** to solve the Knapsack-style problem of lineup construction.
    *   Constraints: Salary caps, roster positions, team stacking rules, and exposure limits.

## � Key Features

*   **Multi-Model Projections**: Doesn't rely on a single algorithm. Uses a weighted ensemble to reduce variance.
*   **EV Betting Analysis**: Automatically compares internal projections against Vegas implied prop lines to identify market inefficiencies.
*   **Dynamic Lineup Generation**: Supports massive lineup generation (150-max) with diversity constraints to avoid fragile, correlated portfolios.
*   **Backtesting Suite**: Includes tools to replay historical weeks and verify model accuracy against actual results.

## 🛠 Installation & Usage

### Prerequisites
*   Python 3.10+
*   PostgreSQL (or Docker)
*   API Keys for data providers (optional for historical backtesting)

### Local Setup

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/hueyfreemancodes/LuckyLines.git
    cd LuckyLines
    ```

2.  **Environment Configuration**
    Copy the example environment file and configure your database credentials.
    ```bash
    cp .env.example .env
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Initialize Database**
    Run the migrations to set up the schema.
    ```bash
    alembic upgrade head
    ```

5.  **Start the API**
    ```bash
    uvicorn app.main:app --reload
    ```
    Access the interactive API docs at `http://localhost:8000/docs`.

### Running with Docker

For a complete stack (App + DB):
```bash
docker-compose up -d --build
```

## 📊 Core Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/players` | Retrieve the master player list for a slate. |
| `POST` | `/api/v1/optimization/optimize` | Submit constraints to generate optimal lineups. |
| `GET` | `/api/v1/projections/nfl/{season}/{week}` | Fetch model projections for a specific week. |
| `POST` | `/api/v1/training/train` | Trigger an asynchronous model retraining job. |

## 🧪 Model Training

To retrain the prop betting models with the latest data:

```bash
python scripts/train_prop_models.py
```

This will output performance metrics (MAE, RMSE) and save the serialized models to the `models/` directory.

---

**Disclaimer**: This software is for educational and analytical purposes only. LuckyLines does not guarantee profit and is not responsible for any financial losses incurred from betting or DFS contests. Gamble responsibly.
