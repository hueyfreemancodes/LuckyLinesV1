"""add_game_id_and_side_to_betting_lines

Revision ID: 9b8a12e35df4
Revises: f55ca88acbc1
Create Date: 2025-11-20 14:39:38.668143

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b8a12e35df4'
down_revision = 'f55ca88acbc1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add game_id column
    op.add_column('betting_lines', sa.Column('game_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_betting_lines_game_id'), 'betting_lines', ['game_id'], unique=False)
    op.create_foreign_key(None, 'betting_lines', 'games', ['game_id'], ['id'])
    
    # Add side column
    op.add_column('betting_lines', sa.Column('side', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove side column
    op.drop_column('betting_lines', 'side')
    
    # Remove game_id column
    op.drop_constraint(None, 'betting_lines', type_='foreignkey')
    op.drop_index(op.f('ix_betting_lines_game_id'), table_name='betting_lines')
    op.drop_column('betting_lines', 'game_id')
