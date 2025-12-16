import sys
import os
import logging
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.projections import ProjectionsService
from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, Player

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backtest_season(season=2024):
    logger.info(f"Starting Backtest for Season {season}...")
    
    service = ProjectionsService()
    db = SessionLocal()
    
    all_predictions = []
    all_actuals = []
    
    # Prop Metrics
    prop_predictions = {
        'passing_yards': [], 'rushing_yards': [], 'receiving_yards': []
    }
    prop_actuals = {
        'passing_yards': [], 'rushing_yards': [], 'receiving_yards': []
    }
    
    # Metrics per week
    weekly_metrics = []
    
    try:
        # Iterate through weeks
        # We'll skip Week 1 because we need history for EMAs
        for week in range(2, 19):
            logger.info(f"Processing Week {week}...")
            
            projections = service.generate_projections(season, week)
            
            if not projections:
                logger.warning(f"No projections generated for Week {week}")
                continue
                
            # 2. Get Actuals
            player_ids = [p['id'] for p in projections]
            
            actuals_query = db.query(PlayerGameStats).filter(
                PlayerGameStats.season == season,
                PlayerGameStats.week == week,
                PlayerGameStats.player_id.in_(player_ids)
            ).all()
            
            actual_map = {
                p.player_id: {
                    'fantasy_points_ppr': p.fantasy_points_ppr,
                    'passing_yards': p.passing_yards,
                    'rushing_yards': p.rushing_yards,
                    'receiving_yards': p.receiving_yards
                } for p in actuals_query
            }
            
            # 3. Compare
            week_preds = []
            week_acts = []
            
            for proj in projections:
                pid = proj['id']
                actual = actual_map.get(pid)
                
                if actual:
                    # Fantasy Points
                    all_predictions.append(proj['points'])
                    all_actuals.append(actual['fantasy_points_ppr'])
                    
                    week_preds.append(proj['points'])
                    week_acts.append(actual['fantasy_points_ppr'])
                    
                    # Props
                    # Passing (only for QBs)
                    if proj['position'] == 'QB':
                        prop_predictions['passing_yards'].append(proj['pass_yds'])
                        prop_actuals['passing_yards'].append(actual['passing_yards'])
                        
                    # Rushing (RB, QB, WR)
                    if proj['position'] in ['RB', 'QB', 'WR'] and proj['rush_yds'] > 0:
                        prop_predictions['rushing_yards'].append(proj['rush_yds'])
                        prop_actuals['rushing_yards'].append(actual['rushing_yards'])
                        
                    # Receiving (WR, TE, RB)
                    if proj['position'] in ['WR', 'TE', 'RB'] and proj['rec_yds'] > 0:
                        prop_predictions['receiving_yards'].append(proj['rec_yds'])
                        prop_actuals['receiving_yards'].append(actual['receiving_yards'])
            
            if week_preds:
                mae = mean_absolute_error(week_acts, week_preds)
                logger.info(f"Week {week} Fantasy MAE: {mae:.2f}")
                weekly_metrics.append({"week": week, "mae": mae, "count": len(week_preds)})
                
        # Overall Metrics
        if all_predictions:
            total_mae = mean_absolute_error(all_actuals, all_predictions)
            r2 = r2_score(all_actuals, all_predictions)
            
            logger.info("\n=== BACKTEST RESULTS (2024) ===")
            logger.info(f"Total Samples: {len(all_predictions)}")
            logger.info(f"Overall Fantasy MAE: {total_mae:.2f}")
            logger.info(f"Fantasy R2 Score: {r2:.3f}")
            
            logger.info("\n--- Prop Model Performance ---")
            for prop, preds in prop_predictions.items():
                acts = prop_actuals[prop]
                if preds:
                    prop_mae = mean_absolute_error(acts, preds)
                    prop_r2 = r2_score(acts, preds)
                    logger.info(f"{prop.replace('_', ' ').title()}: MAE {prop_mae:.2f} | R2 {prop_r2:.3f} | Count {len(preds)}")
            
            # Breakdown by Week
            df_weekly = pd.DataFrame(weekly_metrics)
            print("\nWeekly Breakdown (Fantasy):")
            print(df_weekly.to_string(index=False))
            
    finally:
        db.close()

if __name__ == "__main__":
    backtest_season(2024)
