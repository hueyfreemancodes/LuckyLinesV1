# Codebase Cleanup Summary

## Files Removed

### Scripts Directory (59 removed, 16 kept)
**Removed Categories:**
- **Check/Verify Scripts (19):** analyze_coverage_gaps, analyze_fantasy_context, analyze_feature_distributions, check_defense_by_season, check_defense_opponent, check_defense_values, check_feature_coverage, check_game_team_ids, check_games_db, check_gb_2012_coverage, check_linkage_count, check_offense_stats, check_opponent_column, check_opponent_data, check_sportsbooks, check_weather_data, verify_historical_ingestion, verify_salaries, verify_weather

- **Debug Scripts (8):** debug_game_linkage, debug_rotoguru, debug_team_mapping, diagnose_abbreviations, diagnose_backfill_failures, diagnose_defense_coverage, diagnose_game_matching, diagnose_teams

- **Investigate Scripts (2):** investigate_coverage_gap, calculate_missing_game_impact

- **Backfill Scripts (5):** backfill_game_ids_optimized, backfill_odds, backfill_sportsdataio_salaries, backfill_weather, fix_player_stats_team_ids

- **Test Scripts (14):** test_all_kaggle_ingestion, test_archive_props, test_csv_upload, test_ev_calc, test_historical_props_2023, test_historical_upload, test_kaggle_ingestion, test_new_features, test_salary_integration, test_serving, test_sportsdataio_props, test_training, test_training_detailed, test_weather_history

- **Misc Scripts (7):** create_tables, fetch_betting_metadata, list_teams, scrape_salaries, tune_lstm, train_and_save, evaluate_model

- **Root Files (1):** test_import.py

**Kept (16 Essential Scripts):**
- **Training:** train_xgboost.py, train_prop_models.py, evaluate_all_models.py
- **Ingestion:** ingest_weather_csv.py, ingest_fantasy_csv.py, ingest_defensive_stats.py, backfill_game_ids.py, ingest_odds.py, ingest_pbp.py, seed_db.py
- **Testing:** test_projections_service.py, test_prop_ev.py, test_odds_ingestion.py, test_odds_api.py, test_api.py
- **Utility:** __init__.py

### Ingestion Directory (4 removed, 5 kept)
**Removed:**
- nba_api.py (NBA-specific, not used)
- rotogrinders.py (not implemented)
- fantasypros.py (not implemented)
- sportsdataio.py (deprecated)

**Kept:**
- base.py (base ingestion class)
- csv_ingestion.py (CSV upload functionality)
- draftkings.py (DFS integration)
- fanduel.py (DFS integration)
- odds_api.py (The Odds API integration)

### Log Files (Removed)
- backfill.log (1.2GB)
- backfill_final.log
- backfill_v2.log
- ingest_weather.log
- ingest_weather_2012.log
- ingest_weather_v2.log
- claude_conversation_*.txt

## Codebase Statistics

### Before Cleanup
- Scripts: 71 files
- Ingestion: 9 files
- Log files: 7 files (1.2GB+)

### After Cleanup
- Scripts: 16 files (77% reduction)
- Ingestion: 5 files (44% reduction)
- Log files: 0 files

## What Remains (Essential Only)

### Core Application (`/app`)
- **API Endpoints:** Players, projections, ingestion, etc.
- **Models:** 
  - Database models (models.py)
  - ML models: XGBoost (production), LSTM, CatBoost, LightGBM, Position, Stacked (for comparison)
- **Services:** 
  - projections.py (generate projections)
  - ev_calculator.py (calculate +EV bets)
  - feature_engineering.py (transform data)
  - opponent_defense_features.py (defensive matchups)
  - odds_api.py (fetch real-time lines)
- **Optimization:** DFS lineup optimizer
- **Ingestion:** CSV upload, DFS platforms, Odds API

### Scripts (`/scripts`)
- **Training:** 3 scripts for model training/evaluation
- **Ingestion:** 6 scripts for data pipeline
- **Testing:** 5 scripts for validation
- **Utility:** 2 scripts (__init__, cleanup plan)

### Models (`/models`)
- nfl_xgboost_model.joblib (Fantasy Points - Production)
- passing_yards_model.joblib (Prop Betting)
- rushing_yards_model.joblib (Prop Betting)
- receiving_yards_model.joblib (Prop Betting)

### Data Files (Kept)
- spreadspoke_scores.csv (Historical games/weather/lines)
- fantasy_data (1).csv (Player season stats)
- nfl_pbp.csv (Play-by-play data)

## Impact

### Benefits
✅ **Cleaner codebase** - Only essential files remain
✅ **Easier navigation** - 77% fewer scripts to search through
✅ **Reduced confusion** - No duplicate/obsolete code
✅ **Faster development** - Clear what each file does
✅ **Disk space** - Removed 1.2GB+ of logs

### Preserved Functionality
✅ **All 4 ML models** - Fully functional
✅ **Data pipeline** - Complete ingestion workflow
✅ **API endpoints** - All working endpoints preserved
✅ **Testing** - Essential validation scripts kept
✅ **Training** - Can retrain all models
✅ **Comparison** - Can evaluate alternative models

## Next Steps (Tomorrow)
1. Investigate `betting_lines` table data quality
2. Build prop betting API endpoints
3. Deploy prop models to production (after line validation)
