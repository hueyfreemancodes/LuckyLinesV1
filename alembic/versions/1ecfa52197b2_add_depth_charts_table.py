"""add_depth_charts_table

Revision ID: 1ecfa52197b2
Revises: 9b8a12e35df4
Create Date: 2025-11-20 15:22:02.553063

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1ecfa52197b2'
down_revision = '9b8a12e35df4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('depth_charts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=True),
        sa.Column('week', sa.Integer(), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('position', sa.String(), nullable=True),
        sa.Column('depth_position', sa.String(), nullable=True),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('player_name', sa.String(), nullable=True),
        sa.Column('jersey_number', sa.String(), nullable=True),
        sa.Column('elias_id', sa.String(), nullable=True),
        sa.Column('gsis_id', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_depth_charts_season'), 'depth_charts', ['season'], unique=False)
    op.create_index(op.f('ix_depth_charts_team_id'), 'depth_charts', ['team_id'], unique=False)
    op.create_index(op.f('ix_depth_charts_week'), 'depth_charts', ['week'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_depth_charts_week'), table_name='depth_charts')
    op.drop_index(op.f('ix_depth_charts_team_id'), table_name='depth_charts')
    op.drop_index(op.f('ix_depth_charts_season'), table_name='depth_charts')
    op.drop_table('depth_charts')
