"""Add Celery task tracking fields to episodes table

Revision ID: 008
Revises: 007
Create Date: 2026-03-17 00:00:00.000000

Adds three fields to the Episode model for Celery background job tracking:
1. task_id (Text, indexed) - Celery task UUID
2. task_started_at (DateTime, nullable) - Task submission time
3. task_completed_at (DateTime, nullable) - Task completion time

These fields enable:
- Task status queries by task UUID
- Task cancellation via revoke(task_id)
- Performance monitoring (queue wait + generation time)
- Failure recovery and task retry
- Real-time progress updates to users

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Add task_id column for Celery task UUID
	op.add_column(
		'episodes',
		sa.Column('task_id', sa.Text(), nullable=True),
	)

	# Add task_started_at column
	op.add_column(
		'episodes',
		sa.Column('task_started_at', sa.DateTime(timezone=True), nullable=True),
	)

	# Add task_completed_at column
	op.add_column(
		'episodes',
		sa.Column('task_completed_at', sa.DateTime(timezone=True), nullable=True),
	)

	# Create index on task_id for fast lookups by Celery task UUID
	op.create_index(
		'idx_episodes_task_id',
		'episodes',
		['task_id'],
	)


def downgrade() -> None:
	op.drop_index('idx_episodes_task_id', table_name='episodes')
	op.drop_column('episodes', 'task_completed_at')
	op.drop_column('episodes', 'task_started_at')
	op.drop_column('episodes', 'task_id')
