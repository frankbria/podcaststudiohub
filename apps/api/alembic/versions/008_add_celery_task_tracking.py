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
	# Nullable adds are metadata-only (no table rewrite). if_not_exists makes
	# reruns safe: the adds commit when the autocommit block below opens, so
	# a failed CONCURRENTLY build would otherwise wedge the re-run (#318).

	# Add task_id column for Celery task UUID
	op.add_column(
		'episodes',
		sa.Column('task_id', sa.Text(), nullable=True),
		if_not_exists=True,
	)

	# Add task_started_at column
	op.add_column(
		'episodes',
		sa.Column('task_started_at', sa.DateTime(timezone=True), nullable=True),
		if_not_exists=True,
	)

	# Add task_completed_at column
	op.add_column(
		'episodes',
		sa.Column('task_completed_at', sa.DateTime(timezone=True), nullable=True),
		if_not_exists=True,
	)

	# Create index on task_id for fast lookups by Celery task UUID.
	# episodes pre-exists and may be large: build CONCURRENTLY in an
	# autocommit block so the build never blocks writes (issue #318).
	with op.get_context().autocommit_block():
		op.execute("DROP INDEX IF EXISTS idx_episodes_task_id")
		op.create_index(
			'idx_episodes_task_id',
			'episodes',
			['task_id'],
			postgresql_concurrently=True,
		)


def downgrade() -> None:
	op.drop_index('idx_episodes_task_id', table_name='episodes')
	op.drop_column('episodes', 'task_completed_at')
	op.drop_column('episodes', 'task_started_at')
	op.drop_column('episodes', 'task_id')
