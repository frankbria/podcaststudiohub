"""Add Celery task tracking fields to episodes

Revision ID: 005
Revises: 004
Create Date: 2026-03-05 00:00:00.000000

Adds three fields to the Episode model for Celery background job tracking:
1. task_id (Text, nullable, indexed) - Celery task UUID
2. task_started_at (DateTime with timezone, nullable) - Task submission time
3. task_completed_at (DateTime with timezone, nullable) - Task completion time

These fields enable:
- Task status queries via task_id lookup
- Task cancellation via celery.control.revoke(task_id)
- Performance monitoring (task_completed_at - task_started_at)
- Failure recovery (find failed tasks and retry)
- Real-time progress updates for users

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Add task_id column — stores Celery task UUID for lookup and cancellation
	op.add_column(
		'episodes',
		sa.Column('task_id', sa.Text(), nullable=True)
	)

	# Add task_started_at column — when the task was submitted to Celery
	op.add_column(
		'episodes',
		sa.Column('task_started_at', sa.DateTime(timezone=True), nullable=True)
	)

	# Add task_completed_at column — when the task finished (success or failure)
	op.add_column(
		'episodes',
		sa.Column('task_completed_at', sa.DateTime(timezone=True), nullable=True)
	)

	# Create index on task_id for fast task-status queries and cancellation lookups
	op.create_index(
		'idx_episodes_task_id',
		'episodes',
		['task_id'],
		postgresql_using='btree',
	)


def downgrade() -> None:
	op.drop_index('idx_episodes_task_id', table_name='episodes')

	op.drop_column('episodes', 'task_completed_at')
	op.drop_column('episodes', 'task_started_at')
	op.drop_column('episodes', 'task_id')
