# Weekly Roster Sync Automation

## Overview
Automated weekly sync of NFL rosters and depth charts from NFLverse to keep player team assignments current throughout the season.

## Cron Job Setup

### Option 1: Host Machine Cron (Recommended)

**Schedule:** Every Monday at 6:00 AM

**Crontab Entry:**
```bash
# Edit crontab
crontab -e

# Add this line:
0 6 * * 1 cd /Users/mylescobb/Desktop/LuckyLines && docker-compose exec -T api sh -c "export PYTHONPATH=. && python scripts/sync_rosters_nflverse.py --year 2025" >> /Users/mylescobb/Desktop/LuckyLines/logs/roster_sync.log 2>&1
```

**Explanation:**
- `0 6 * * 1` = Every Monday at 6:00 AM
- `-T` flag = Run without TTY (required for cron)
- `>> logs/roster_sync.log` = Append output to log file
- `2>&1` = Redirect errors to same log

### Option 2: Docker Container Cron

**Create cron file inside container:**

1. **Add cron to Dockerfile:**
```dockerfile
# Install cron
RUN apt-get update && apt-get install -y cron

# Copy cron file
COPY crontab /etc/cron.d/roster-sync
RUN chmod 0644 /etc/cron.d/roster-sync
RUN crontab /etc/cron.d/roster-sync
```

2. **Create `crontab` file:**
```bash
# /Users/mylescobb/Desktop/LuckyLines/crontab
0 6 * * 1 cd /app && python scripts/sync_rosters_nflverse.py --year 2024 >> /var/log/roster_sync.log 2>&1
```

3. **Rebuild container:**
```bash
docker-compose up -d --build
```

### Option 3: Celery Beat (Production)

**For production deployment with Celery:**

1. **Create Celery task:**
```python
# app/tasks/roster_sync.py
from celery import Celery
from scripts.sync_rosters_nflverse import sync_rosters_from_nflverse, sync_depth_charts_from_nflverse

@celery.task
def weekly_roster_sync():
    sync_rosters_from_nflverse(2024)
    sync_depth_charts_from_nflverse(2024)
```

2. **Schedule in Celery Beat:**
```python
# app/celery_config.py
from celery.schedules import crontab

beat_schedule = {
    'weekly-roster-sync': {
        'task': 'app.tasks.roster_sync.weekly_roster_sync',
        'schedule': crontab(hour=6, minute=0, day_of_week=1),  # Monday 6 AM
    },
}
```

## Manual Execution

### Full Sync (Rosters + Depth Charts)
```bash
docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/sync_rosters_nflverse.py --year 2024"
```

### Rosters Only
```bash
docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/sync_rosters_nflverse.py --year 2024 --rosters-only"
```

### Depth Charts Only (Specific Week)
```bash
docker-compose exec api sh -c "export PYTHONPATH=. && python scripts/sync_rosters_nflverse.py --year 2024 --week 12 --depth-charts-only"
```

## Monitoring

### Check Last Sync
```bash
tail -n 50 /Users/mylescobb/Desktop/LuckyLines/logs/roster_sync.log
```

### Verify Roster Updates
```bash
docker-compose exec api sh -c "export PYTHONPATH=. && python -c \"
from app.core.database import SessionLocal
from app.models.models import Player, Team

db = SessionLocal()
chubb = db.query(Player).filter(Player.first_name == 'Nick', Player.last_name == 'Chubb').first()
team = db.query(Team).filter(Team.id == chubb.team_id).first()
print(f'Nick Chubb: {team.name}')
db.close()
\""
```

### Check Depth Chart Data
```bash
docker-compose exec api sh -c "export PYTHONPATH=. && python -c \"
from app.core.database import SessionLocal
from app.models.models import DepthChart

db = SessionLocal()
count = db.query(DepthChart).filter(DepthChart.season == 2024).count()
print(f'Depth chart entries for 2024: {count}')
db.close()
\""
```

## Logs Directory Setup

```bash
# Create logs directory
mkdir -p /Users/mylescobb/Desktop/LuckyLines/logs

# Set permissions
chmod 755 /Users/mylescobb/Desktop/LuckyLines/logs
```

## Troubleshooting

### Cron Not Running
```bash
# Check cron service status
sudo systemctl status cron

# View cron logs
grep CRON /var/log/syslog
```

### Permission Issues
```bash
# Ensure script is executable
chmod +x /Users/mylescobb/Desktop/LuckyLines/scripts/sync_rosters_nflverse.py

# Check Docker permissions
docker-compose exec api whoami
```

### Package Not Found
```bash
# Reinstall nfl-data-py
docker-compose exec api pip install nfl-data-py
```

## Recommended: Option 1 (Host Machine Cron)

For simplicity and reliability, use **Option 1** with host machine cron. This ensures:
- Runs even if container restarts
- Easy to monitor via log files
- No need to modify Docker setup
- Simple to enable/disable

## Next Steps

1. Set up cron job (Option 1 recommended)
2. Create logs directory
3. Test manual execution
4. Monitor first automated run on Monday
5. Verify roster updates after each sync
