"""
Opponent Defensive Strength Feature Engineering

This module adds opponent defensive strength features to the model.
Uses TeamGameDefenseStats to calculate rolling defensive metrics.
"""

import pandas as pd
import numpy as np

def calculate_rolling_defense_stats(defense_stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate rolling defensive metrics (last 4 games) for all teams.
    """
    # Drop duplicates to ensure unique index (e.g. if normalization merged teams)
    defense_stats_df = defense_stats_df.drop_duplicates(subset=['team', 'season', 'week'])
    defense_stats_df = defense_stats_df.sort_values(['team', 'season', 'week'])
    
    # Points allowed per game (lower is better defense)
    defense_stats_df['def_ppg_allowed_last4'] = defense_stats_df.groupby('team')['points_allowed'].transform(
        lambda x: x.rolling(window=4, min_periods=1).mean()
    )
    
    # Yards allowed per game (lower is better defense)
    defense_stats_df['def_ypg_allowed_last4'] = defense_stats_df.groupby('team')['yards_allowed'].transform(
        lambda x: x.rolling(window=4, min_periods=1).mean()
    )
    
    # Sacks per game (higher is better defense)
    defense_stats_df['def_sacks_per_game_last4'] = defense_stats_df.groupby('team')['sacks'].transform(
        lambda x: x.rolling(window=4, min_periods=1).mean()
    )
    
    # Turnovers per game (interceptions + fumbles recovered)
    defense_stats_df['turnovers'] = defense_stats_df['interceptions'] + defense_stats_df['fumbles_recovered']
    defense_stats_df['def_turnovers_per_game_last4'] = defense_stats_df.groupby('team')['turnovers'].transform(
        lambda x: x.rolling(window=4, min_periods=1).mean()
    )
    
    # Calculate Strength Score (0-1 scale)
    # We can calculate this here since it depends only on the rolling metrics
    # Use default values for missing data to avoid NaNs
    ppg = defense_stats_df['def_ppg_allowed_last4'].fillna(25.0)
    ypg = defense_stats_df['def_ypg_allowed_last4'].fillna(350.0)
    sacks = defense_stats_df['def_sacks_per_game_last4'].fillna(2.5)
    turnovers = defense_stats_df['def_turnovers_per_game_last4'].fillna(1.5)
    
    defense_stats_df['opp_def_strength_score'] = (
        (1 - (ppg - 10) / 30) * 0.4 +
        (1 - (ypg - 250) / 200) * 0.3 +
        (sacks / 5) * 0.15 +
        (turnovers / 3) * 0.15
    ).clip(0, 1)
    
    return defense_stats_df

def calculate_opponent_defense_features(df: pd.DataFrame, defense_stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate opponent defensive strength features.
    
    Args:
        df: PlayerGameStats dataframe with 'opponent', 'season', 'week' columns
        defense_stats_df: TeamGameDefenseStats dataframe
    
    Returns:
        DataFrame with added opponent defense features
    """
    # Ensure we have required columns
    if 'opponent' not in df.columns:
        df['opponent'] = None
    
    # Calculate rolling defensive metrics (last 4 games)
    defense_stats_df = calculate_rolling_defense_stats(defense_stats_df)
    
    # Create lookup map: (opponent_team, season, week) -> defensive metrics
    defense_lookup = defense_stats_df.set_index(['team', 'season', 'week'])[[
        'def_ppg_allowed_last4',
        'def_ypg_allowed_last4', 
        'def_sacks_per_game_last4',
        'def_turnovers_per_game_last4',
        'opp_def_strength_score'
    ]].to_dict('index')
    
    # Add opponent defense features to player stats
    def get_opponent_defense(row):
        key = (row['opponent'], row['season'], row['week'])
        return defense_lookup.get(key, {})
    
    opponent_defense = df.apply(get_opponent_defense, axis=1, result_type='expand')
    
    # Add features with default values
    df['opp_def_ppg_allowed'] = opponent_defense.get('def_ppg_allowed_last4', pd.Series([25.0] * len(df)))
    df['opp_def_ypg_allowed'] = opponent_defense.get('def_ypg_allowed_last4', pd.Series([350.0] * len(df)))
    df['opp_def_sacks_per_game'] = opponent_defense.get('def_sacks_per_game_last4', pd.Series([2.5] * len(df)))
    df['opp_def_turnovers_per_game'] = opponent_defense.get('def_turnovers_per_game_last4', pd.Series([1.5] * len(df)))
    
    # Normalize features (0-1 scale)
    # Lower PPG allowed = tougher defense = lower score for offense
    df['opp_def_strength_score'] = (
        (1 - (df['opp_def_ppg_allowed'] - 10) / 30) * 0.4 +  # PPG (40% weight)
        (1 - (df['opp_def_ypg_allowed'] - 250) / 200) * 0.3 +  # YPG (30% weight)
        (df['opp_def_sacks_per_game'] / 5) * 0.15 +  # Sacks (15% weight)
        (df['opp_def_turnovers_per_game'] / 3) * 0.15  # Turnovers (15% weight)
    ).clip(0, 1)
    
    return df


# Add to FeatureEngineering class
@staticmethod
def calculate_opponent_defense_features_static(df: pd.DataFrame) -> pd.DataFrame:
    """
    Placeholder for opponent defense features.
    Actual calculation happens in training/prediction pipeline.
    """
    # Ensure columns exist with defaults
    for col in ['opp_def_ppg_allowed', 'opp_def_ypg_allowed', 
                'opp_def_sacks_per_game', 'opp_def_turnovers_per_game',
                'opp_def_strength_score']:
        if col not in df.columns:
            df[col] = 0.0
    
    return df
