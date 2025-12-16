import sys
import os
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.ev_calculator import EVService

logging.basicConfig(level=logging.INFO)

def main():
    db = SessionLocal()
    try:
        service = EVService(db)
        print("Running EV Analysis for 2025 Week 14...")
    # Run Analysis
        bets = service.find_best_bets(season=2025, week=14)
    
        if not bets:
            print("No +EV bets found.")
        else:
            print(f"\nFound {len(bets)} +EV bets.")
            
            # Categorize
            categories = {
                'player_pass_yds': {'Over': [], 'Under': []},
                'player_rush_yds': {'Over': [], 'Under': []},
                'player_reception_yds': {'Over': [], 'Under': []}
            }
            
            for bet in bets:
                market = bet['market']
                side = bet['bet_type'] # Over/Under
                # Map market keys if needed (assuming standard keys)
                if market in categories:
                    categories[market][side].append(bet)
                    
            # Print Top 5 for each category
            for market, sides in categories.items():
                print(f"\n=== {market.replace('_', ' ').title()} ===")
                for side, side_bets in sides.items():
                    print(f"\n  Top 5 {side}s:")
                    # Sort by EV descending
                    sorted_bets = sorted(side_bets, key=lambda x: x['ev_percent'], reverse=True)[:5]
                    
                    if not sorted_bets:
                        print("    None found.")
                        continue
                        
                    print(f"    {'Player':<25} {'Line':<6} {'Proj':<6} {'Diff':<6} {'EV%':<6} {'Book':<10}")
                    print("    " + "-"*65)
                    for b in sorted_bets:
                        print(f"    {b['player_name']:<25} {b['line']:<6.1f} {b['projection']:<6.1f} {b['diff']:<6.1f} {b['ev_percent']:<6.1f} {b['bookmaker']:<10}")
                
    finally:
        db.close()

if __name__ == "__main__":
    main()
