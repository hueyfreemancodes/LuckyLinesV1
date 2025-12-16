import pandas as pd
import logging
from typing import List, Dict, Any
from app.core.database import SessionLocal
from app.models.models import PlayerGameStats, Player, TeamGameOffenseStats, TeamGameDefenseStats, Team, VegasLine
from app.services.opponent_defense_features import calculate_rolling_defense_stats
from app.models.projections.xgboost_model import XGBoostModel

logger = logging.getLogger(__name__)

class ProjectionsService:
    """
    Service to manage model lifecycle and generate projections.
    """
    
    def __init__(self):
        self.model = XGBoostModel(target_col='fantasy_points_ppr')
        self.pass_model = XGBoostModel(target_col='passing_yards')
        self.rush_model = XGBoostModel(target_col='rushing_yards')
        self.rec_model = XGBoostModel(target_col='receiving_yards')
        
        # Try to load existing models
        try:
            self.model.load("nfl_xgboost_model.joblib")
            self.pass_model.load("passing_yards_model.joblib")
            self.rush_model.load("rushing_yards_model.joblib")
            self.rec_model.load("receiving_yards_model.joblib")
        except FileNotFoundError:
            logger.warning("One or more trained models not found. Projections may be incomplete.")

    def generate_projections(self, season: int, week: int) -> List[Dict[str, Any]]:
        """
        Generates projections for a specific week.
        Fetches necessary historical data for feature engineering (EMAs, Lags).
        """
        db = SessionLocal()
        try:
            # 1. Fetch Data
            # We need history for EMAs (span=4) and Lags (1). 
            # Fetching 5-6 weeks prior is sufficient.
            lookback = 6
            
            # Fetch current season data
            query = db.query(PlayerGameStats, Player).join(Player, PlayerGameStats.player_id == Player.id).filter(
                PlayerGameStats.season == season,
                PlayerGameStats.week <= week
            )
            results = query.all()
            
            # Fetch Team Stats for current season
            team_stats_query = db.query(TeamGameOffenseStats).filter(
                TeamGameOffenseStats.season == season
            ).all()
            
            # Check if we need previous season data (if week is early)
            if week <= lookback:
                prev_season = season - 1
                start_week_prev = 18 - lookback
                if start_week_prev < 1: start_week_prev = 1
                
                logger.info(f"Fetching context from Season {prev_season} (Weeks {start_week_prev}-18)")
                
                query_prev = db.query(PlayerGameStats, Player).join(Player, PlayerGameStats.player_id == Player.id).filter(
                    PlayerGameStats.season == prev_season,
                    PlayerGameStats.week >= start_week_prev
                )
                results.extend(query_prev.all())
                
                # Fetch Team Stats for previous season
                team_stats_prev = db.query(TeamGameOffenseStats).filter(
                    TeamGameOffenseStats.season == prev_season,
                    TeamGameOffenseStats.week >= start_week_prev
                ).all()
                team_stats_query.extend(team_stats_prev)

            team_stats_data = [{
                "team_name": ts.team_name, "season": ts.season, "week": ts.week,
                "pass_attempts": ts.pass_attempts, "rush_attempts": ts.rush_attempts
            } for ts in team_stats_query]
            team_stats_df = pd.DataFrame(team_stats_data)
            
            # Fetch Teams for mapping IDs to Abbreviations
            teams = db.query(Team).all()
            team_id_map = {t.id: t.abbreviation for t in teams}
            
            # Abbreviation Normalization Map
            ABBR_MAP = {
                'JAC': 'JAX', 'STL': 'LAR', 'SL': 'LAR', 'SD': 'LAC', 'SDG': 'LAC',
                'OAK': 'LV', 'LVR': 'LV', 'LAS': 'LV', 'TAM': 'TB', 'TBB': 'TB',
                'KAN': 'KC', 'KNC': 'KC', 'NWE': 'NE', 'NOR': 'NO', 'SFO': 'SF',
                'GNB': 'GB', 'GRE': 'GB', 'WSH': 'WAS', 'HST': 'HOU', 'CLV': 'CLE',
                'BLT': 'BAL', 'ARZ': 'ARI', 'LA': 'LAR'
            }
            def normalize_abbr(abbr):
                if not abbr: return None
                return ABBR_MAP.get(abbr, abbr)
            
            # Fetch Team Defense Stats for Opponent Features
            defense_stats_query = db.query(TeamGameDefenseStats).filter(
                TeamGameDefenseStats.season == season
            ).all()
            defense_stats_data = [{
                "team": normalize_abbr(ds.team_name), "season": ds.season, "week": ds.week,
                "points_allowed": ds.points_allowed, "yards_allowed": ds.yards_allowed,
                "sacks": ds.sacks, "interceptions": ds.interceptions, 
                "fumbles_recovered": ds.fumbles_recovered
            } for ds in defense_stats_query]
            defense_stats_df = pd.DataFrame(defense_stats_data)
            
            # Calculate rolling stats
            if not defense_stats_df.empty:
                defense_stats_df = calculate_rolling_defense_stats(defense_stats_df)
                # Create lookup map for target week
                target_week_defense = defense_stats_df[defense_stats_df['week'] == week]
                defense_map = target_week_defense.set_index('team').to_dict('index')
            else:
                defense_map = {}
            
            if not results:
                logger.warning(f"No data found for Season {season} Week {week}")
                return []

            # Fetch Games for Weather
            # We need to map game_id from PlayerGameStats to Game.
            # Currently PlayerGameStats has game_id.
            # Let's fetch all games for this season/week to build a map.
            from app.models.models import Game, PlayerSeasonStats
            
            games_query = db.query(Game).filter(
                Game.season == season,
                Game.week <= week # Fetch history too if needed, but for weather we mainly need current week for projection
            ).all()
            
            # Map game_id -> Game object
            game_map = {g.id: g for g in games_query}
            
            # Fetch Vegas Lines for these games
            vegas_lines = db.query(VegasLine).filter(
                VegasLine.game_id.in_(game_map.keys())
            ).all()
            vegas_map = {vl.game_id: vl for vl in vegas_lines}
            
            # Fetch Player Season Stats (Previous Season) for VORP/PPG Baseline
            prev_season_stats = db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.season == season - 1
            ).all()
            
            # Map player_id -> Stats
            season_stats_map = {s.player_id: s for s in prev_season_stats}

            # Fetch Slate for this week (Assuming DK Main Slate for now)
            # In future, pass platform/slate_id as arg
            from app.models.models import Slate, PlayerSlate
            
            slate = db.query(Slate).filter(
                Slate.platform == "DraftKings",
                Slate.name.like(f"%Week {week}%")
            ).first()
            
            # Create a map of player_id -> salary
            salary_map = {}
            if slate:
                player_slates = db.query(PlayerSlate).filter(PlayerSlate.slate_id == slate.id).all()
                for ps in player_slates:
                    salary_map[ps.player_id] = ps.salary
            
            data = []
            for stats, player in results:
                # Get salary from map or default
                salary = salary_map.get(player.id, 5000)
                
                # Get Game/Weather
                game = game_map.get(stats.game_id)
                wind = game.forecast_wind_speed if game else 0
                temp = game.forecast_temp_low if game else 50
                humidity = game.forecast_humidity if game else 0
                
                # Get Vegas Lines
                v_line = vegas_map.get(stats.game_id)
                vegas_total = v_line.total_points if v_line else 0.0
                vegas_spread = v_line.spread if v_line else 0.0
                
                # Get Season Stats (VORP/PPG)
                p_stats = season_stats_map.get(player.id)
                vorp = p_stats.vorp if p_stats else 0.0
                ppg_last = p_stats.ppg_half_ppr if p_stats else 0.0 # Using half ppr as proxy if full not stored, or calc full
                
                # Determine Opponent
                opponent = None
                if game:
                    home_team = team_id_map.get(game.home_team_id)
                    away_team = team_id_map.get(game.away_team_id)
                    # stats.team is usually abbreviation.
                    if stats.team == home_team:
                        opponent = normalize_abbr(away_team)
                    elif stats.team == away_team:
                        opponent = normalize_abbr(home_team)
                        
                # Lookup Opponent Defense Stats
                opp_stats = defense_map.get(opponent, {})
                opp_def_ppg = opp_stats.get('def_ppg_allowed_last4', 25.0)
                opp_def_ypg = opp_stats.get('def_ypg_allowed_last4', 350.0)
                opp_def_sacks = opp_stats.get('def_sacks_per_game_last4', 2.5)
                opp_def_turnovers = opp_stats.get('def_turnovers_per_game_last4', 1.5)
                opp_def_score = opp_stats.get('opp_def_strength_score', 0.5)
                
                data.append({
                    "fantasy_points_ppr": stats.fantasy_points_ppr,
                    "salary": salary,
                    "team": stats.team,
                    "season": stats.season,
                    "week": stats.week,
                    "player_id": stats.player_id,
                    "player_name": f"{player.first_name} {player.last_name}",
                    "position": player.position,
                    "is_home": 1 if stats.is_home else 0,
                    # Features needed for engineering
                    "pass_attempts": stats.pass_attempts,
                    "pass_completions": stats.pass_completions,
                    "passing_yards": stats.passing_yards,
                    "passing_tds": stats.passing_tds,
                    "interceptions": stats.interceptions,
                    "rush_attempts": stats.rush_attempts,
                    "rushing_yards": stats.rushing_yards,
                    "rushing_tds": stats.rushing_tds,
                    "targets": stats.targets,
                    "receptions": stats.receptions,
                    "receiving_yards": stats.receiving_yards,
                    "receiving_tds": stats.receiving_tds,
                    "red_zone_targets": stats.red_zone_targets,
                    "red_zone_pass_attempts": stats.red_zone_pass_attempts,
                    "red_zone_rush_attempts": stats.red_zone_rush_attempts,
                    # New Data
                    "forecast_wind_speed": wind,
                    "forecast_temp_low": temp,
                    "forecast_humidity": humidity,
                    "vegas_total": vegas_total,
                    "vegas_spread": vegas_spread,
                    "vorp_last_season": vorp,
                    "ppg_last_season": ppg_last,
                    # Opponent Defense Features
                    "opp_def_ppg_allowed": opp_def_ppg,
                    "opp_def_ypg_allowed": opp_def_ypg,
                    "opp_def_sacks_per_game": opp_def_sacks,
                    "opp_def_turnovers_per_game": opp_def_turnovers,
                    "opp_def_strength_score": opp_def_score
                })
                
            df = pd.DataFrame(data)
            
            # 2. Generate Projections
            # XGBoost predicts on the dataframe directly.
            # prepare_features inside predict will handle sorting and feature calc.
            
            # Ensure we sort by player/season/week for correct lag/ema calculation inside model
            df = df.sort_values(['player_id', 'season', 'week'])
            
            predictions = self.model.predict(df, team_stats_df)
            
            # Assign predictions back to DF
            df['projected_points'] = predictions
            
            # Generate Stat Projections
            try:
                df['proj_pass_yds'] = self.pass_model.predict(df, team_stats_df)
            except:
                df['proj_pass_yds'] = 0.0
                
            try:
                df['proj_rush_yds'] = self.rush_model.predict(df, team_stats_df)
            except:
                df['proj_rush_yds'] = 0.0
                
            try:
                df['proj_rec_yds'] = self.rec_model.predict(df, team_stats_df)
            except:
                df['proj_rec_yds'] = 0.0
            
            # Filter for the requested week
            target_week_df = df[df['week'] == week]
            
            # Filter out inactive players
            # Query PlayerGameStats for status in target week
            inactive_statuses = ['INA', 'RES', 'CUT', 'TRC']
            player_ids_in_week = target_week_df['player_id'].unique().tolist()
            
            inactive_query = db.query(PlayerGameStats.player_id).filter(
                PlayerGameStats.season == season,
                PlayerGameStats.week == week,
                PlayerGameStats.player_id.in_(player_ids_in_week),
                PlayerGameStats.status.in_(inactive_statuses)
            ).all()
            
            inactive_player_ids = {pid for (pid,) in inactive_query}
            
            logger.info(f"Filtering out {len(inactive_player_ids)} inactive players for Week {week}")
            
            output = []
            for _, row in target_week_df.iterrows():
                # Skip inactive players
                if row['player_id'] in inactive_player_ids:
                    continue
                    
                if pd.notna(row.get('projected_points')):
                    output.append({
                        "id": row['player_id'],
                        "name": row['player_name'],
                        "position": row['position'],
                        "team": row['team'],
                        "salary": row['salary'],
                        "points": float(row['projected_points']),
                        "pass_yds": float(row['proj_pass_yds']),
                        "rush_yds": float(row['proj_rush_yds']),
                        "rec_yds": float(row['proj_rec_yds'])
                    })
            
            return output

        except Exception as e:
            logger.error(f"Error generating projections: {e}")
            return []
        finally:
            db.close()
