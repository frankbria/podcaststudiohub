"""Add render tracking fields to episode_compositions

Adds composed_duration_seconds, render_status, render_error, and last_rendered_at
columns to episode_compositions table to support the composition render workflow.

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
    # Add render tracking fields to episode_compositions
    op.add_column(
        'episode_compositions',
        sa.Column('composed_duration_seconds', sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        'episode_compositions',
        sa.Column('render_status', sa.Text(), nullable=True)
    )
    op.add_column(
        'episode_compositions',
        sa.Column('render_error', sa.Text(), nullable=True)
    )
    op.add_column(
        'episode_compositions',
        sa.Column('last_rendered_at', sa.TIMESTAMP(timezone=True), nullable=True)
    )

    # Add index on render_status for efficient querying
    op.create_index(
        'idx_episode_compositions_render_status',
        'episode_compositions',
        ['render_status']
    )

    # Add check constraint for render_status values
    op.execute(
        "ALTER TABLE episode_compositions ADD CONSTRAINT render_status_check "
        "CHECK (render_status IS NULL OR render_status IN ('pending', 'composing', 'complete', 'failed'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE episode_compositions DROP CONSTRAINT IF EXISTS render_status_check"
    )
    op.drop_index('idx_episode_compositions_render_status', table_name='episode_compositions')
    op.drop_column('episode_compositions', 'last_rendered_at')
    op.drop_column('episode_compositions', 'render_error')
    op.drop_column('episode_compositions', 'render_status')
    op.drop_column('episode_compositions', 'composed_duration_seconds')
