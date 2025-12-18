import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class FeatureEngineering:
    """
    Service for generating advanced features for NFL projections.
    """

    @staticmethod
    def _group_shift(df, col, span=None, lag=None):
        """Helper to apply EWM or Shift by player."""
        grouped = df.groupby('player_id')[col]
        if span:
            # Shift 1 to use entering stats
            return grouped.transform(lambda x: x.ewm(span=span, adjust=False).mean().shift(1))
        if lag:
            return grouped.shift(lag)
        return None

    @classmethod
    def add_emas(cls, df: pd.DataFrame, span: int = 4, cols: list = None) -> pd.DataFrame:
        if not cols: return df
        df = df.sort_values(['player_id', 'season', 'week'])
        
        for col in [c for c in cols if c in df.columns]:
            df[f'{col}_ema_{span}'] = cls._group_shift(df, col, span=span).fillna(0)
        return df

    @classmethod
    def add_lags(cls, df: pd.DataFrame, lags: list = [1], cols: list = None) -> pd.DataFrame:
        if not cols: return df
        df = df.sort_values(['player_id', 'season', 'week'])

        for col in cols:
            for lag in lags:
                df[f'{col}_lag_{lag}'] = cls._group_shift(df, col, lag=lag).fillna(0)
        return df

    @classmethod
    def calc_streak(cls, df: pd.DataFrame, metric='fantasy_points_ppr', short=3, long=8) -> pd.DataFrame:
        """Ratio of short-term to long-term EMA. >1 = hot."""
        df = df.sort_values(['player_id', 'season', 'week'])
        
        short_ema = cls._group_shift(df, metric, span=short)
        long_ema = cls._group_shift(df, metric, span=long)
        
        # Avoid div/0
        df['streak_coefficient'] = np.where(long_ema > 0, short_ema / long_ema, 1.0)
        return df.fillna({'streak_coefficient': 1.0})

    @classmethod
    def calc_velocity(cls, df: pd.DataFrame, metric='fantasy_points_ppr', short=2, long=8) -> pd.DataFrame:
        """Delta between short and long term EMA."""
        df = df.sort_values(['player_id', 'season', 'week'])
        short_ema = cls._group_shift(df, metric, span=short)
        long_ema = cls._group_shift(df, metric, span=long)
        
        df[f'{metric}_velocity'] = (short_ema - long_ema).fillna(0.0)
        return df

    @staticmethod
    def add_team_shares(df: pd.DataFrame, team_stats: pd.DataFrame) -> pd.DataFrame:
        """Calculates Target/Rush shares relative to team totals."""
        cols = ['team_name', 'season', 'week', 'pass_attempts', 'rush_attempts']
        # Map abbreviations if needed, for now assume clean
        
        merged = df.merge(
            team_stats[cols],
            left_on=['team', 'season', 'week'],
            right_on=['team_name', 'season', 'week'],
            how='left', suffixes=('', '_team')
        )
        
        # Vectorized share calc
        for share, num, den in [
            ('target_share', 'targets', 'pass_attempts_team'),
            ('rush_share', 'rush_attempts', 'rush_attempts_team')
        ]:
            merged[share] = np.where(
                merged[den] > 0, merged[num] / merged[den], 0.0
            ) 
            
        return merged.fillna({'target_share': 0.0, 'rush_share': 0.0})

    @staticmethod
    def add_rz_share(df: pd.DataFrame, team_stats: pd.DataFrame = None) -> pd.DataFrame:
        """Red Zone opportunity share."""
        # Aggregate team RZ opportunities on the fly from player data
        # (Assuming team_stats doesn't have it yet)
        rz_cols = ['red_zone_pass_attempts', 'red_zone_rush_attempts', 'red_zone_targets']
        
        team_rz = df.groupby(['team', 'season', 'week'])[rz_cols].sum().reset_index()
        team_rz['team_rz_ops'] = team_rz['red_zone_pass_attempts'] + team_rz['red_zone_rush_attempts']
        
        merged = df.merge(
            team_rz[['team', 'season', 'week', 'team_rz_ops']],
            on=['team', 'season', 'week'], how='left'
        )
        
        player_ops = merged['red_zone_targets'] + merged['red_zone_rush_attempts']
        merged['red_zone_share'] = np.where(
            merged['team_rz_ops'] > 0, player_ops / merged['team_rz_ops'], 0.0
        )
        return merged.fillna({'red_zone_share': 0.0})

    @staticmethod
    def add_opp_share(df: pd.DataFrame, team_stats: pd.DataFrame) -> pd.DataFrame:
        """Overall opportunity share (Types + Rushes) / Team Plays."""
        cols = ['team_name', 'season', 'week', 'pass_attempts', 'rush_attempts']
        merged = df.merge(
            team_stats[cols],
            left_on=['team', 'season', 'week'],
            right_on=['team_name', 'season', 'week'],
            how='left', suffixes=('', '_tm')
        )
        
        total_plays = merged['pass_attempts_tm'] + merged['rush_attempts_tm']
        player_ops = merged['targets'] + merged['rush_attempts']
        
        merged['opportunity_share'] = np.where(
            total_plays > 0, player_ops / total_plays, 0.0
        )
        return merged.fillna({'opportunity_share': 0.0})

    @staticmethod
    def add_vegas_implied(df: pd.DataFrame) -> pd.DataFrame:
        """(Total/2) - (Spread/2)."""
        if 'vegas_total' not in df or 'vegas_spread' not in df:
            df['implied_team_total'] = 0.0
            return df
            
        # Standard: spread is negative for favorite (e.g. -3.5)
        # Fav implied: (Total - (-3.5)) / 2  ?? No
        # Fav implied: (Total / 2) - (Spread / 2) -> (25) - (-1.75) = 26.75
        df['implied_team_total'] = (df['vegas_total'] - df['vegas_spread']) / 2
        return df

    @staticmethod
    def add_game_script_features(df: pd.DataFrame) -> pd.DataFrame:
        if 'vegas_spread' not in df: 
            return df.assign(spread_passing_interaction=0.0, spread_rushing_interaction=0.0)
            
        # Interaction terms
        # If underdog (spread > 0), passing volume might scale up
        pass_ema = df.get('passing_yards_ema_4', 0)
        rush_ema = df.get('rushing_yards_ema_4', 0)
        
        df['spread_passing_interaction'] = df['vegas_spread'] * pass_ema
        # If favorite (spread < 0), rushing scales up. Invert spread so favorability is positive
        df['spread_rushing_interaction'] = -1 * df['vegas_spread'] * rush_ema
        return df

    @staticmethod
    def add_weather_impact(df: pd.DataFrame) -> pd.DataFrame:
        """Position-specific weather penalties/boosts."""
        # Defaults
        for c in ['forecast_wind_speed', 'forecast_temp_low', 'forecast_humidity']:
            if c not in df: df[c] = 0.0
            
        pos = df.get('position', 'UNK')
        wind = df['forecast_wind_speed'].fillna(0)
        
        # Penalties/Boosts
        # Passers hate wind
        df['weather_wind_passing_penalty'] = np.where(
            pos.isin(['QB', 'WR', 'TE']),
            (wind / 15.0).clip(0, 2), 0.0
        )
        
        # Rushers might benefit (game script shift)
        df['weather_wind_rushing_boost'] = np.where(
            pos == 'RB',
            ((wind - 10) / 10.0).clip(0, 1), 0.0
        )
        
        df['weather_temp_extreme'] = ((df['forecast_temp_low'] < 32) | (df['forecast_temp_low'] > 90)).astype(float)
        df['weather_high_humidity'] = (df['forecast_humidity'] > 70).astype(float)
        
        return df

    @staticmethod
    def add_fantasy_context(df: pd.DataFrame) -> pd.DataFrame:
        """VORP and PPG trends."""
        # Defaults
        for c in ['vorp_last_season', 'ppg_last_season']:
            if c not in df: df[c] = 0.0
            
        # PPG Trend
        curr = df.get('fantasy_points_ppr_ema_4', 0)
        df['player_ppg_trend'] = curr - df['ppg_last_season']
        
        # Binning helper
        def bin_col(col, bins):
            return pd.cut(col, bins=[-float('inf')] + bins + [float('inf')], labels=[0, 1, 2, 3]).fillna(1.0).astype(float)
        
        df['vorp_tier'] = bin_col(df['vorp_last_season'], [-99, -52, 7])
        df['ppg_tier'] = bin_col(df['ppg_last_season'], [4, 8.7, 13.7])
        df['ppg_last_season_squared'] = df['ppg_last_season'] ** 2
        
        return df
    
    @staticmethod
    def add_xfp(df: pd.DataFrame) -> pd.DataFrame:
        """Expected Fantasy Points model."""
        from sklearn.linear_model import LinearRegression
        
        feats = ['targets', 'rush_attempts', 'red_zone_targets', 'red_zone_rush_attempts']
        target = 'fantasy_points_ppr'
        
        # Ensure cols
        for f in feats: 
            if f not in df: df[f] = 0.0
            
        # Train on non-nulls
        mask = df[target].notna() & (df[target] != 0)
        
        if mask.sum() > 100:
            X = df.loc[mask, feats].fillna(0)
            y = df.loc[mask, target].fillna(0)
            model = LinearRegression().fit(X, y)
            df['xFP'] = model.predict(df[feats].fillna(0))
        else:
            # Fallback coefficients
            df['xFP'] = (
                df['targets'] * 1.5 + 
                df['rush_attempts'] * 0.6 + 
                df['red_zone_targets'] * 1.0 + 
                df['red_zone_rush_attempts'] * 1.5
            )
            
        df['xFP_diff'] = df.get(target, 0) - df['xFP']
        return df

    @staticmethod
    def add_def_features(df: pd.DataFrame) -> pd.DataFrame:
        # Placeholder for opponent stats join
        defaults = [
            'opp_def_ppg_allowed', 'opp_def_ypg_allowed', 
            'opp_def_sacks_per_game', 'opp_def_turnovers_per_game',
            'opp_def_strength_score'
        ]
        for c in defaults:
            if c not in df: df[c] = 0.0
        return df

    @staticmethod
    def add_streaks(df: pd.DataFrame, metric='fantasy_points_ppr', threshold=15.0) -> pd.DataFrame:
        """Consecutive games over threshold."""
        df = df.sort_values(['player_id', 'season', 'week'])
        
        def _streak_calc(s):
            # Shift 1 to use entering stats
            shifted = s.shift(1).fillna(False)
            # Group by change in boolean value to identify blocks
            # But we want *cumulative* streak.
            # Fast vectorized approach for cumulative streaks of True:
            # Reset sum at False
            y = shifted.astype(int)
            return y * (y.groupby((y != y.shift()).cumsum()).cumcount() + 1)
            
        df[f'{metric}_streak_over_{int(threshold)}'] = df.groupby('player_id')[metric].transform(
            lambda x: _streak_calc(x >= threshold)
        )
        return df
