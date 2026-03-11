"""Add render status fields to episode_compositions

Adds render_status, render_error, last_rendered_at, and composed_duration_seconds
to episode_compositions to track the render lifecycle and composed audio metadata.

Revision ID: 007
Revises: 006
Create Date: 2026-03-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Add render lifecycle columns to episode_compositions
	op.add_column(
		'episode_compositions',
		sa.Column('render_status', sa.Text(), nullable=False, server_default='draft')
	)
	op.add_column(
		'episode_compositions',
		sa.Column('render_error', sa.Text(), nullable=True)
	)
	op.add_column(
		'episode_compositions',
		sa.Column('last_rendered_at', sa.DateTime(), nullable=True)
	)
	op.add_column(
		'episode_compositions',
		sa.Column('composed_duration_seconds', sa.Numeric(10, 2), nullable=True)
	)
	op.create_index(
		'idx_episode_compositions_render_status',
		'episode_compositions',
		['render_status']
	)


def downgrade() -> None:
	op.drop_index('idx_episode_compositions_render_status', table_name='episode_compositions')
	op.drop_column('episode_compositions', 'composed_duration_seconds')
	op.drop_column('episode_compositions', 'last_rendered_at')
	op.drop_column('episode_compositions', 'render_error')
	op.drop_column('episode_compositions', 'render_status')
