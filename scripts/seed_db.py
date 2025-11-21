import sys
import os
import random
from datetime import datetime, timedelta

# Add the parent directory to sys.path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine
from app.models import models

def seed_db():
    db = SessionLocal()
    
    # Check if data exists
    if db.query(models.Sport).first():
        print("Database already seeded.")
        return

    print("Seeding database...")

    # 1. Sports
    nfl = models.Sport(name="NFL", is_active=True)
    nba = models.Sport(name="NBA", is_active=True)
    db.add_all([nfl, nba])
    db.commit()

    # 2. Teams (NFL)
    teams = [
        {"city": "Kansas City", "name": "Chiefs", "abbr": "KC"},
        {"city": "San Francisco", "name": "49ers", "abbr": "SF"},
        {"city": "Baltimore", "name": "Ravens", "abbr": "BAL"},
        {"city": "Detroit", "name": "Lions", "abbr": "DET"},
        {"city": "Buffalo", "name": "Bills", "abbr": "BUF"},
        {"city": "Philadelphia", "name": "Eagles", "abbr": "PHI"},
    ]
    
    db_teams = []
    for t in teams:
        team = models.Team(sport_id=nfl.id, name=f"{t['city']} {t['name']}", abbreviation=t['abbr'])
        db.add(team)
        db_teams.append(team)
    db.commit()

    # 3. Players
    positions = ["QB", "RB", "WR", "TE", "DST"]
    players = []
    
    for team, team_data in zip(db_teams, teams):
        # Create a QB
        players.append(models.Player(
            sport_id=nfl.id, team_id=team.id, 
            first_name=f"{team.abbreviation}", last_name="Quarterback", 
            position="QB"
        ))
        # Create 2 RBs
        for i in range(2):
            players.append(models.Player(
                sport_id=nfl.id, team_id=team.id, 
                first_name=f"{team.abbreviation}", last_name=f"RunningBack {i+1}", 
                position="RB"
            ))
        # Create 3 WRs
        for i in range(3):
            players.append(models.Player(
                sport_id=nfl.id, team_id=team.id, 
                first_name=f"{team.abbreviation}", last_name=f"Receiver {i+1}", 
                position="WR"
            ))
        # Create 1 TE
        players.append(models.Player(
            sport_id=nfl.id, team_id=team.id, 
            first_name=f"{team.abbreviation}", last_name="TightEnd", 
            position="TE"
        ))
        # Create DST
        players.append(models.Player(
            sport_id=nfl.id, team_id=team.id, 
            first_name=f"{team_data['city']}", last_name="Defense", 
            position="DST"
        ))

    db.add_all(players)
    db.commit()

    # 4. Slates
    slate = models.Slate(
        sport_id=nfl.id, 
        platform="DraftKings", 
        name="Main Slate", 
        start_time=datetime.now() + timedelta(days=1),
        external_id="slate_123"
    )
    db.add(slate)
    db.commit()

    # 5. PlayerSlates & Projections
    for player in players:
        salary = random.randint(3000, 9000)
        points = random.uniform(5.0, 30.0)
        
        # Adjust based on position for realism
        if player.position == "QB":
            salary += 1000
            points += 10
        
        ps = models.PlayerSlate(
            player_id=player.id,
            slate_id=slate.id,
            salary=salary,
            roster_position=player.position,
            is_available=True
        )
        db.add(ps)
        
        proj = models.Projection(
            player_id=player.id,
            slate_id=slate.id,
            source="consensus",
            points=round(points, 2),
            ceiling=round(points * 1.5, 2),
            floor=round(points * 0.5, 2)
        )
        db.add(proj)

    db.commit()
    print("Database seeded successfully!")

if __name__ == "__main__":
    seed_db()
