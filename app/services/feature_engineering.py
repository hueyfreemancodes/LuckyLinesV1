import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class FeatureEngineering:
    """
    Service for generating advanced features for NFL projections.
    """
    
    @staticmethod
    def calculate_exponential_moving_averages(df: pd.DataFrame, span: int = 4, columns: list = None) -> pd.DataFrame:
        """
        Calculates Exponential Moving Averages (EMA) for specified columns grouped by player.
        """
        if columns is None:
            return df
            
        # Ensure data is sorted by date/week
        df = df.sort_values(by=['player_id', 'season', 'week'])
        
        for col in columns:
            if col in df.columns:
                # Group by player and apply EMA
                # shift(1) because we want the average *entering* the game, not including the game itself
                df[f'{col}_ema_{span}'] = df.groupby('player_id')[col].transform(
                    lambda x: x.ewm(span=span, adjust=False).mean().shift(1)
                ).fillna(0)
                
        return df

    @staticmethod
    def calculate_lag_features(df: pd.DataFrame, lags: list = [1], columns: list = None) -> pd.DataFrame:
        """
        Creates lag features (e.g., points_last_week).
        """
        if columns is None:
            return df
            
        df = df.sort_values(by=['player_id', 'season', 'week'])
        
        for col in columns:
            for lag in lags:
                df[f'{col}_lag_{lag}'] = df.groupby('player_id')[col].shift(lag).fillna(0)
                
        return df

    @staticmethod
    def calculate_streak_coefficient(df: pd.DataFrame, metric: str = 'fantasy_points_ppr', short_span: int = 3, long_span: int = 8) -> pd.DataFrame:
        """
        Calculates a 'streak coefficient' by comparing short-term EMA to long-term EMA.
        Ratio > 1.0 implies 'hot', < 1.0 implies 'cold'.
        """
        df = df.sort_values(by=['player_id', 'season', 'week'])
        
        # Calculate EMAs (shifted to be predictive)
        short_ema = df.groupby('player_id')[metric].transform(
            lambda x: x.ewm(span=short_span, adjust=False).mean().shift(1)
        )
        long_ema = df.groupby('player_id')[metric].transform(
            lambda x: x.ewm(span=long_span, adjust=False).mean().shift(1)
        )
        
        # Avoid division by zero
        df['streak_coefficient'] = np.where(long_ema > 0, short_ema / long_ema, 1.0)
        df['streak_coefficient'] = df['streak_coefficient'].fillna(1.0)
        
        return df

    @staticmethod
    def calculate_team_shares(player_df: pd.DataFrame, team_stats_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Target Share and Rush Share for each player relative to their team totals.
        """
        # Merge player stats with team stats on (team, season, week)
        # Note: team_stats_df needs to be pre-processed to have matching keys
        
        # Ensure join keys match types
        merged = pd.merge(
            player_df,
            team_stats_df[['team_name', 'season', 'week', 'pass_attempts', 'rush_attempts']],
            left_on=['team', 'season', 'week'],
            right_on=['team_name', 'season', 'week'],
            how='left',
            suffixes=('', '_team')
        )
        
        # Target Share (Targets / Team Pass Attempts)
        merged['target_share'] = np.where(
            merged['pass_attempts_team'] > 0,
            merged['targets'] / merged['pass_attempts_team'],
            0.0
        )
        
        # Rush Share (Rush Attempts / Team Rush Attempts)
        merged['rush_share'] = np.where(
            merged['rush_attempts_team'] > 0,
            merged['rush_attempts'] / merged['rush_attempts_team'],
            0.0
        )
        
        # Fill NaNs
        merged['target_share'] = merged['target_share'].fillna(0.0)
        merged['rush_share'] = merged['rush_share'].fillna(0.0)
        
        return merged

    @staticmethod
    def calculate_red_zone_share(player_df: pd.DataFrame, team_stats_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Red Zone Opportunity Share:
        (Player RZ Targets + Player RZ Rushes) / (Team RZ Pass Attempts + Team RZ Rush Attempts)
        """
        # We need team RZ stats. If team_stats_df doesn't have them aggregated yet, 
        # we might need to aggregate from player stats or assume they are passed in.
        # Currently TeamGameOffenseStats doesn't have RZ columns, but we can aggregate from players.
        
        # For now, let's assume we aggregate team RZ stats from the player_df itself 
        # since we just ingested RZ stats into PlayerGameStats.
        
        # Group by Team/Season/Week to get Team RZ Totals
        team_rz = player_df.groupby(['team', 'season', 'week'])[[
            'red_zone_pass_attempts', 'red_zone_rush_attempts', 'red_zone_targets'
        ]].sum().reset_index()
        
        team_rz['team_rz_opportunities'] = team_rz['red_zone_pass_attempts'] + team_rz['red_zone_rush_attempts']
        
        # Merge back to player DF
        merged = pd.merge(
            player_df,
            team_rz[['team', 'season', 'week', 'team_rz_opportunities']],
            on=['team', 'season', 'week'],
            how='left'
        )
        
        player_ops = merged['red_zone_targets'] + merged['red_zone_rush_attempts']
        
        merged['red_zone_share'] = np.where(
            merged['team_rz_opportunities'] > 0,
            player_ops / merged['team_rz_opportunities'],
            0.0
        )
        
        merged['red_zone_share'] = merged['red_zone_share'].fillna(0.0)
        return merged

    @staticmethod
    def calculate_opportunity_share(player_df: pd.DataFrame, team_stats_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Overall Opportunity Share:
        (Player Targets + Player Rush Attempts) / (Team Pass Attempts + Team Rush Attempts)
        """
        # Merge if not already merged (or re-merge to be safe)
        merged = pd.merge(
            player_df,
            team_stats_df[['team_name', 'season', 'week', 'pass_attempts', 'rush_attempts']],
            left_on=['team', 'season', 'week'],
            right_on=['team_name', 'season', 'week'],
            how='left',
            suffixes=('', '_team_opp')
        )
        
        team_plays = merged['pass_attempts_team_opp'] + merged['rush_attempts_team_opp']
        player_ops = merged['targets'] + merged['rush_attempts']
        
        merged['opportunity_share'] = np.where(
            team_plays > 0,
            player_ops / team_plays,
            0.0
        )
        
        merged['opportunity_share'] = merged['opportunity_share'].fillna(0.0)
        return merged

    @staticmethod
    def calculate_implied_totals(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates implied team total from Vegas lines.
        Formula: (OverUnder / 2) - (Spread / 2) if favorite, else + (Spread / 2)
        
        Requires columns: 'vegas_total', 'vegas_spread', 'is_favorite'
        """
        if 'vegas_total' not in df.columns or 'vegas_spread' not in df.columns:
            df['implied_team_total'] = 0.0 # Default if missing
            return df
            
        # Assuming spread is negative for favorite (e.g., -3.5)
        # Favorite Total = (Total / 2) + (Abs(Spread) / 2) -> Wait, standard is (Total/2) - (Spread/2) where spread is negative?
        # Let's use standard logic:
        # Favorite (-X): (Total + X) / 2  (e.g. 50, -10 -> (50+10)/2 = 30)
        # Underdog (+X): (Total - X) / 2  (e.g. 50, +10 -> (50-10)/2 = 20)
        
        # If spread is always relative to "this team":
        # If spread is -3.5 (Favorite), Total 40 -> (40 - (-3.5))/2 = 21.75
        # If spread is +3.5 (Underdog), Total 40 -> (40 - 3.5)/2 = 18.25
        
        df['implied_team_total'] = (df['vegas_total'] - df['vegas_spread']) / 2
        return df

    @staticmethod
    def calculate_velocity(df: pd.DataFrame, metric: str = 'fantasy_points_ppr', short_span: int = 2, long_span: int = 8) -> pd.DataFrame:
        """
        Calculates 'Velocity of Change' (Delta): Difference between short-term and long-term EMA.
        Positive delta = trending up.
        """
        df = df.sort_values(by=['player_id', 'season', 'week'])
        
        short_ema = df.groupby('player_id')[metric].transform(
            lambda x: x.ewm(span=short_span, adjust=False).mean().shift(1)
        )
        long_ema = df.groupby('player_id')[metric].transform(
            lambda x: x.ewm(span=long_span, adjust=False).mean().shift(1)
        )
        
        df[f'{metric}_velocity'] = short_ema - long_ema
        df[f'{metric}_velocity'] = df[f'{metric}_velocity'].fillna(0.0)
        
        return df

    @staticmethod
    def calculate_consecutive_streaks(df: pd.DataFrame, metric: str = 'fantasy_points_ppr', threshold: float = 15.0) -> pd.DataFrame:
        """
        Calculates the number of consecutive games where the metric >= threshold.
        """
        df = df.sort_values(by=['player_id', 'season', 'week'])
        
        # Create a boolean series for the condition
        condition = df[metric] >= threshold
        
        # Group by player and calculate streak
        # Logic: Compare current row with previous to identify streak breaks
        # shift(1) to use *previous* games for prediction (we don't know if they hit 15 today yet)
        # Wait, streak entering the game is based on *past* games.
        
        def get_streak(series):
            # Series of booleans
            # We want the streak *entering* the current index.
            # So we shift first.
            shifted = series.shift(1).fillna(False)
            
            streaks = []
            current_streak = 0
            for val in shifted:
                if val:
                    current_streak += 1
                else:
                    current_streak = 0
                streaks.append(current_streak)
            return pd.Series(streaks, index=series.index)

        # Use transform instead of apply to ensure alignment
        # But transform works on Series, apply works on DataFrame/Series
        # Let's iterate groups manually to be safe or use a different approach
        
        # Faster vectorized approach:
        # 1. Identify where condition is False (streak breaks)
        df[f'{metric}_streak_over_{int(threshold)}'] = df.groupby('player_id')[metric].transform(
            lambda x: get_streak(x >= threshold)
        )
        
        return df

    @staticmethod
    def calculate_weather_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates position-specific weather features.
        High wind affects passing (QB/WR/TE) more than rushing (RB).
        Requires: 'forecast_wind_speed', 'forecast_temp_low', 'forecast_humidity', 'position'
        """
        # Ensure columns exist
        for col in ['forecast_wind_speed', 'forecast_temp_low', 'forecast_humidity']:
            if col not in df.columns:
                df[col] = 0.0
        
        # Get position from player_id if not in df
        if 'position' not in df.columns:
            df['position'] = 'UNKNOWN'
        
        # 1. Position-Specific Wind Impact
        # QB/WR/TE are negatively affected by high wind (less passing)
        # RB is less affected or may benefit (more rushing)
        df['wind_speed'] = df['forecast_wind_speed'].fillna(0)
        
        # Passing positions (QB, WR, TE) - negative impact from wind
        df['weather_wind_passing_penalty'] = 0.0
        passing_positions = df['position'].isin(['QB', 'WR', 'TE'])
        df.loc[passing_positions, 'weather_wind_passing_penalty'] = (
            df.loc[passing_positions, 'wind_speed'] / 15.0  # Normalize to 0-2 range
        ).clip(0, 2)
        
        # Rushing positions (RB) - potential benefit from wind (more rushing attempts)
        df['weather_wind_rushing_boost'] = 0.0
        rushing_positions = df['position'] == 'RB'
        df.loc[rushing_positions, 'weather_wind_rushing_boost'] = (
            (df.loc[rushing_positions, 'wind_speed'] - 10) / 10.0  # Boost starts at 10mph
        ).clip(0, 1)
        
        # 2. Extreme Temperature (affects all positions)
        df['weather_temp_extreme'] = (
            (df['forecast_temp_low'] < 32) | (df['forecast_temp_low'] > 90)
        ).astype(float)
        
        # 3. High Humidity (affects ball grip, all positions)
        df['weather_high_humidity'] = (
            df['forecast_humidity'] > 70
        ).astype(float)
        
        return df

    @staticmethod
    def calculate_fantasy_context_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates features based on historical fantasy context (VORP, PPG trends).
        Requires: 'vorp_last_season', 'ppg_last_season', 'fantasy_points_ppr_ema_4'
        """
        # Ensure columns exist
        for col in ['vorp_last_season', 'ppg_last_season']:
            if col not in df.columns:
                df[col] = 0.0
                
        # 1. VORP Last Season (Direct) - already in vorp_last_season
        
        # 2. PPG Trend (Current EMA - Last Season PPG)
        # Are they overperforming or underperforming their baseline?
        if 'fantasy_points_ppr_ema_4' in df.columns:
            df['player_ppg_trend'] = df['fantasy_points_ppr_ema_4'] - df['ppg_last_season']
        else:
            df['player_ppg_trend'] = 0.0
        
        # 3. VORP Tier (Categorical bins based on analysis)
        # Bottom 25%: < -99, Q2: -99 to -52, Q3: -52 to 7, Top 25%: > 7
        df['vorp_tier'] = pd.cut(
            df['vorp_last_season'],
            bins=[-float('inf'), -99, -52, 7, float('inf')],
            labels=[0, 1, 2, 3]  # 0=Bottom, 3=Top
        ).astype(float)
        df['vorp_tier'] = df['vorp_tier'].fillna(1.0)  # Default to Q2
        
        # 4. PPG Tier (Categorical bins based on analysis)
        # Bottom 25%: < 4, Q2: 4 to 8.7, Q3: 8.7 to 13.7, Top 25%: > 13.7
        df['ppg_tier'] = pd.cut(
            df['ppg_last_season'],
            bins=[-float('inf'), 4, 8.7, 13.7, float('inf')],
            labels=[0, 1, 2, 3]  # 0=Bottom, 3=Top
        ).astype(float)
        df['ppg_tier'] = df['ppg_tier'].fillna(1.0)  # Default to Q2
        
        # 5. PPG Squared (Non-linear relationship)
        df['ppg_last_season_squared'] = df['ppg_last_season'] ** 2
        
        return df

    @staticmethod
    def calculate_expected_fantasy_points(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Expected Fantasy Points (xFP) based on opportunity volume.
        Uses a simple Linear Regression to weight Targets, Rushes, and Red Zone opportunities.
        Also calculates xFP_diff (Actual - Expected) to measure efficiency (FPOE).
        """
        from sklearn.linear_model import LinearRegression
        
        # Features for xFP
        features = ['targets', 'rush_attempts', 'red_zone_targets', 'red_zone_rush_attempts']
        target = 'fantasy_points_ppr'
        
        # Ensure columns exist
        for col in features:
            if col not in df.columns:
                df[col] = 0.0
        
        # Filter for training data (rows with actual points)
        train_mask = (df[target].notna()) & (df[target] != 0)
        
        if train_mask.sum() > 100: # Only train if we have enough data
            X = df.loc[train_mask, features].fillna(0)
            y = df.loc[train_mask, target].fillna(0)
            
            model = LinearRegression()
            model.fit(X, y)
            
            # Apply to all rows
            # Fill NaNs in features for prediction as well
            df['xFP'] = model.predict(df[features].fillna(0))
        else:
            # Fallback coefficients
            df['xFP'] = (
                df['targets'] * 1.5 + 
                df['rush_attempts'] * 0.6 + 
                df['red_zone_targets'] * 1.0 + 
                df['red_zone_rush_attempts'] * 1.5
            )
            
        # Calculate Efficiency (FPOE)
        actual_points = df[target].fillna(0)
        df['xFP_diff'] = actual_points - df['xFP']
        
        return df

    @staticmethod
    def calculate_opponent_defense_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Placeholder for opponent defense features.
        Actual calculation happens in training/prediction pipeline with defense_stats.
        """
        # Ensure columns exist with defaults
        for col in ['opp_def_ppg_allowed', 'opp_def_ypg_allowed', 
                    'opp_def_sacks_per_game', 'opp_def_turnovers_per_game',
                    'opp_def_strength_score']:
            if col not in df.columns:
                df[col] = 0.0
        
        return df
