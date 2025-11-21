from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Sport(Base):
    __tablename__ = "sports"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    name = Column(String)
    abbreviation = Column(String, index=True)
    
    sport = relationship("Sport")

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    first_name = Column(String)
    last_name = Column(String)
    position = Column(String)
    external_ids = Column(JSON) # {draftkings: "123", fanduel: "456"}
    
    sport = relationship("Sport")
    team = relationship("Team")

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    game_time = Column(DateTime(timezone=True))
    season = Column(Integer, index=True) # Added for linkage
    week = Column(Integer, index=True)   # Added for linkage
    
    # Weather & Stadium Info
    forecast_wind_speed = Column(Integer, nullable=True)
    forecast_temp_low = Column(Integer, nullable=True)
    forecast_temp_high = Column(Integer, nullable=True)
    forecast_description = Column(String, nullable=True)
    stadium_details = Column(JSON, nullable=True)
    
    sport = relationship("Sport")
    forecast_description = Column(String, nullable=True)
    forecast_humidity = Column(Integer, nullable=True) # Added for historical CSV
    stadium_details = Column(JSON, nullable=True)
    
    sport = relationship("Sport")
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])

class Slate(Base):
    __tablename__ = "slates"
    id = Column(Integer, primary_key=True, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    platform = Column(String) # DraftKings, FanDuel
    name = Column(String)
    start_time = Column(DateTime(timezone=True))
    external_id = Column(String)

class PlayerSlate(Base):
    __tablename__ = "player_slates"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    slate_id = Column(Integer, ForeignKey("slates.id"))
    salary = Column(Integer)
    roster_position = Column(String)
    is_available = Column(Boolean, default=True)
    
    player = relationship("Player")
    slate = relationship("Slate")

class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    season = Column(Integer, index=True)
    team = Column(String)
    position = Column(String)
    age = Column(Integer)
    games_played = Column(Integer)
    games_started = Column(Integer)
    
    # Fantasy
    fantasy_points_half_ppr = Column(Float)
    fantasy_points_ppr = Column(Float) # Calculated
    ppg_half_ppr = Column(Float)
    vorp = Column(Float)
    
    # Raw Stats
    passing_yards = Column(Float, default=0.0)
    passing_tds = Column(Integer, default=0)
    passing_int = Column(Integer, default=0)
    rushing_yards = Column(Float, default=0.0)
    rushing_tds = Column(Integer, default=0)
    receiving_yards = Column(Float, default=0.0)
    receiving_tds = Column(Integer, default=0)
    receptions = Column(Integer, default=0)
    fumbles = Column(Integer, default=0)
    fumbles_lost = Column(Integer, default=0)
    
    player = relationship("Player")

class Projection(Base):
    __tablename__ = "projections"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    slate_id = Column(Integer, ForeignKey("slates.id"))
    source = Column(String) # rotogrinders, fantasypros, internal_model
    points = Column(Float)
    ceiling = Column(Float)
    floor = Column(Float)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class VegasLine(Base):
    __tablename__ = "vegas_lines"
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    source = Column(String)
    total_points = Column(Float)
    spread = Column(Float)
    home_implied_total = Column(Float)
    away_implied_total = Column(Float)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    
    game = relationship("Game")

class PlayerCorrelation(Base):
    __tablename__ = "player_correlations"
    id = Column(Integer, primary_key=True, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))
    player1_pos = Column(String)
    player2_pos = Column(String)
    correlation = Column(Float)
    sample_size = Column(Integer)

class HistoricalPerformance(Base):
    __tablename__ = "historical_performance"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    game_id = Column(Integer, ForeignKey("games.id"))
    points = Column(Float)
    salary = Column(Integer)
    stats = Column(JSON)
    
    player = relationship("Player")
    game = relationship("Game")

class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True) # Can be null if we just use season/week
    
    # Context
    season = Column(Integer, index=True)
    week = Column(Integer, index=True)
    team = Column(String, index=True)
    opponent = Column(String)
    is_home = Column(Boolean)
    status = Column(String, default="ACT") # ACT, INA, RES
    
    # Passing
    pass_attempts = Column(Integer, default=0)
    pass_completions = Column(Integer, default=0)
    passing_yards = Column(Float, default=0.0)
    passing_tds = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    
    # Rushing
    rush_attempts = Column(Integer, default=0)
    rushing_yards = Column(Float, default=0.0)
    rushing_tds = Column(Integer, default=0)
    
    # Receiving
    targets = Column(Integer, default=0)
    receptions = Column(Integer, default=0)
    receiving_yards = Column(Float, default=0.0)
    receiving_tds = Column(Integer, default=0)
    
    # Fantasy
    fantasy_points_ppr = Column(Float, default=0.0)
    fantasy_points_standard = Column(Float, default=0.0)
    
    # Red Zone Stats (Derived from Play-by-Play)
    red_zone_pass_attempts = Column(Integer, default=0)
    red_zone_rush_attempts = Column(Integer, default=0)
    red_zone_targets = Column(Integer, default=0)
    red_zone_passing_tds = Column(Integer, default=0)
    red_zone_rushing_tds = Column(Integer, default=0)
    red_zone_receiving_tds = Column(Integer, default=0)
    
    player = relationship("Player", back_populates="game_stats")
    game = relationship("Game")

# Add relationship to Player model
Player.game_stats = relationship("PlayerGameStats", back_populates="player")
Player.defense_stats = relationship("PlayerGameDefenseStats", back_populates="player")
Player.season_stats = relationship("PlayerSeasonStats", back_populates="player")

class PlayerGameDefenseStats(Base):
    __tablename__ = "player_game_defense_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True)
    
    season = Column(Integer, index=True)
    week = Column(Integer, index=True)
    team = Column(String, index=True)
    
    solo_tackle = Column(Integer, default=0)
    assist_tackle = Column(Integer, default=0)
    sacks = Column(Float, default=0.0)
    qb_hits = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    pass_defended = Column(Integer, default=0)
    fumbles_forced = Column(Integer, default=0)
    fumbles_recovered = Column(Integer, default=0)
    defensive_tds = Column(Integer, default=0)
    safeties = Column(Integer, default=0)
    
    fantasy_points_ppr = Column(Float, default=0.0)
    fantasy_points_standard = Column(Float, default=0.0)
    
    player = relationship("Player", back_populates="defense_stats")
    game = relationship("Game")

class TeamGameOffenseStats(Base):
    __tablename__ = "team_game_offense_stats"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True) # Link if team exists
    team_name = Column(String, index=True) # Store name directly from CSV
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True)
    
    season = Column(Integer, index=True)
    week = Column(Integer, index=True)
    opponent = Column(String)
    
    total_yards = Column(Float, default=0.0)
    pass_attempts = Column(Integer, default=0) # Added for shares
    passing_yards = Column(Float, default=0.0)
    rush_attempts = Column(Integer, default=0) # Added for shares
    rushing_yards = Column(Float, default=0.0)
    total_points = Column(Integer, default=0)
    turnovers = Column(Integer, default=0)
    
    game = relationship("Game")

class TeamGameDefenseStats(Base):
    __tablename__ = "team_game_defense_stats"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    team_name = Column(String, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True)
    
    season = Column(Integer, index=True)
    week = Column(Integer, index=True)
    opponent = Column(String)
    
    points_allowed = Column(Integer, default=0)
    yards_allowed = Column(Float, default=0.0)
    sacks = Column(Float, default=0.0)
    interceptions = Column(Integer, default=0)
    fumbles_recovered = Column(Integer, default=0)
    
    game = relationship("Game")

class Lineup(Base):
    __tablename__ = "lineups"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True) # Placeholder for auth
    slate_id = Column(Integer, ForeignKey("slates.id"))
    sport_id = Column(Integer, ForeignKey("sports.id"))
    players = Column(JSON) # List of player_ids
    total_salary = Column(Integer)
    projected_points = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class OptimizationRequest(Base):
    __tablename__ = "optimization_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    status = Column(String) # pending, completed, failed
    constraints = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SimulationResult(Base):
    __tablename__ = "simulation_results"
    id = Column(Integer, primary_key=True, index=True)
    lineup_id = Column(Integer, ForeignKey("lineups.id"))
    roi = Column(Float)
    win_prob = Column(Float)
    details = Column(JSON)
    
    lineup = relationship("Lineup")

class BettingLine(Base):
    __tablename__ = "betting_lines"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    game_id = Column(Integer, ForeignKey("games.id"), nullable=True, index=True)
    bookmaker = Column(String, index=True) # DraftKings, FanDuel, etc.
    market_key = Column(String, index=True) # player_pass_yds, etc.
    side = Column(String, nullable=True) # "Over" or "Under"
    line = Column(Float)
    odds = Column(Integer) # American odds (-110)
    implied_prob = Column(Float)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    player = relationship("Player")
    game = relationship("Game")

class DepthChart(Base):
    __tablename__ = "depth_charts"
    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    week = Column(Integer, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    position = Column(String) # QB, RB, WR, TE, etc.
    depth_position = Column(String) # QB, RB1, RB2, WR1, WR2, etc.
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    player_name = Column(String) # Store name in case player not in our DB yet
    jersey_number = Column(String, nullable=True)
    elias_id = Column(String, nullable=True)
    gsis_id = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    team = relationship("Team")
    player = relationship("Player")
