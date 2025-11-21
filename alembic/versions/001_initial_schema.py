"""Initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-11-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sports
    op.create_table('sports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sports_id'), 'sports', ['id'], unique=False)
    op.create_index(op.f('ix_sports_name'), 'sports', ['name'], unique=True)

    # Teams
    op.create_table('teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('abbreviation', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_teams_abbreviation'), 'teams', ['abbreviation'], unique=False)
    op.create_index(op.f('ix_teams_id'), 'teams', ['id'], unique=False)

    # Players
    op.create_table('players',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('position', sa.String(), nullable=True),
        sa.Column('external_ids', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_players_id'), 'players', ['id'], unique=False)

    # Games
    op.create_table('games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('game_time', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['away_team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['home_team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_games_id'), 'games', ['id'], unique=False)

    # Slates
    op.create_table('slates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('platform', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_slates_id'), 'slates', ['id'], unique=False)

    # PlayerSlates
    op.create_table('player_slates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('slate_id', sa.Integer(), nullable=True),
        sa.Column('salary', sa.Integer(), nullable=True),
        sa.Column('roster_position', sa.String(), nullable=True),
        sa.Column('is_available', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['slate_id'], ['slates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_player_slates_id'), 'player_slates', ['id'], unique=False)

    # Projections
    op.create_table('projections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('slate_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('points', sa.Float(), nullable=True),
        sa.Column('ceiling', sa.Float(), nullable=True),
        sa.Column('floor', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['slate_id'], ['slates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projections_id'), 'projections', ['id'], unique=False)

    # Vegas Lines
    op.create_table('vegas_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('total_points', sa.Float(), nullable=True),
        sa.Column('spread', sa.Float(), nullable=True),
        sa.Column('home_implied_total', sa.Float(), nullable=True),
        sa.Column('away_implied_total', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vegas_lines_id'), 'vegas_lines', ['id'], unique=False)

    # Player Correlations
    op.create_table('player_correlations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('player1_pos', sa.String(), nullable=True),
        sa.Column('player2_pos', sa.String(), nullable=True),
        sa.Column('correlation', sa.Float(), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_player_correlations_id'), 'player_correlations', ['id'], unique=False)

    # Historical Performance
    op.create_table('historical_performance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('points', sa.Float(), nullable=True),
        sa.Column('salary', sa.Integer(), nullable=True),
        sa.Column('stats', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_historical_performance_id'), 'historical_performance', ['id'], unique=False)

    # Lineups
    op.create_table('lineups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('slate_id', sa.Integer(), nullable=True),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('players', sa.JSON(), nullable=True),
        sa.Column('total_salary', sa.Integer(), nullable=True),
        sa.Column('projected_points', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['slate_id'], ['slates.id'], ),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lineups_id'), 'lineups', ['id'], unique=False)
    op.create_index(op.f('ix_lineups_user_id'), 'lineups', ['user_id'], unique=False)

    # Optimization Requests
    op.create_table('optimization_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('constraints', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_optimization_requests_id'), 'optimization_requests', ['id'], unique=False)

    # Simulation Results
    op.create_table('simulation_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lineup_id', sa.Integer(), nullable=True),
        sa.Column('roi', sa.Float(), nullable=True),
        sa.Column('win_prob', sa.Float(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['lineup_id'], ['lineups.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_simulation_results_id'), 'simulation_results', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_simulation_results_id'), table_name='simulation_results')
    op.drop_table('simulation_results')
    op.drop_index(op.f('ix_optimization_requests_id'), table_name='optimization_requests')
    op.drop_table('optimization_requests')
    op.drop_index(op.f('ix_lineups_user_id'), table_name='lineups')
    op.drop_index(op.f('ix_lineups_id'), table_name='lineups')
    op.drop_table('lineups')
    op.drop_index(op.f('ix_historical_performance_id'), table_name='historical_performance')
    op.drop_table('historical_performance')
    op.drop_index(op.f('ix_player_correlations_id'), table_name='player_correlations')
    op.drop_table('player_correlations')
    op.drop_index(op.f('ix_vegas_lines_id'), table_name='vegas_lines')
    op.drop_table('vegas_lines')
    op.drop_index(op.f('ix_projections_id'), table_name='projections')
    op.drop_table('projections')
    op.drop_index(op.f('ix_player_slates_id'), table_name='player_slates')
    op.drop_table('player_slates')
    op.drop_index(op.f('ix_slates_id'), table_name='slates')
    op.drop_table('slates')
    op.drop_index(op.f('ix_games_id'), table_name='games')
    op.drop_table('games')
    op.drop_index(op.f('ix_players_id'), table_name='players')
    op.drop_table('players')
    op.drop_index(op.f('ix_teams_id'), table_name='teams')
    op.drop_index(op.f('ix_teams_abbreviation'), table_name='teams')
    op.drop_table('teams')
    op.drop_index(op.f('ix_sports_name'), table_name='sports')
    op.drop_index(op.f('ix_sports_id'), table_name='sports')
    op.drop_table('sports')
