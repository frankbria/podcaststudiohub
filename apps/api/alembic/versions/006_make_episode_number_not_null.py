"""Make episode_number NOT NULL with auto-increment per project

Backfills NULL episode_number values with sequential numbers per project
(ordered by created_at ASC), then enforces NOT NULL and adds a unique
constraint on (project_id, episode_number) to guarantee ordering integrity.

Revision ID: 006
Revises: 005
Create Date: 2026-03-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	connection = op.get_bind()

	# Step 1: Backfill NULL episode_numbers.
	# For each project, assign sequential numbers starting from
	# MAX(existing episode_number) + 1 for NULL rows, ordered by created_at.
	# Projects with no existing non-NULL values start from 1.
	backfill_sql = text("""
	WITH project_max AS (
		SELECT project_id, COALESCE(MAX(episode_number), 0) AS max_num
		FROM episodes
		WHERE episode_number IS NOT NULL
		GROUP BY project_id
	),
	null_episodes AS (
		SELECT
			e.id,
			e.project_id,
			ROW_NUMBER() OVER (
				PARTITION BY e.project_id ORDER BY e.created_at ASC
			) + COALESCE(pm.max_num, 0) AS new_number
		FROM episodes e
		LEFT JOIN project_max pm ON e.project_id = pm.project_id
		WHERE e.episode_number IS NULL
	)
	UPDATE episodes e
	SET episode_number = ne.new_number
	FROM null_episodes ne
	WHERE e.id = ne.id
	""")
	connection.execute(backfill_sql)

	# Step 2: Enforce NOT NULL on episode_number.
	op.alter_column(
		'episodes',
		'episode_number',
		existing_type=sa.Integer(),
		nullable=False,
	)

	# Step 3: Add unique constraint per project.
	op.create_unique_constraint(
		'uq_episodes_project_number',
		'episodes',
		['project_id', 'episode_number'],
	)

	# Step 4: Add composite index for efficient ordering queries.
	op.create_index(
		'idx_episodes_project_number',
		'episodes',
		['project_id', 'episode_number'],
	)


def downgrade() -> None:
	op.drop_index('idx_episodes_project_number', table_name='episodes')
	op.drop_constraint('uq_episodes_project_number', 'episodes', type_='unique')
	op.alter_column(
		'episodes',
		'episode_number',
		existing_type=sa.Integer(),
		nullable=True,
	)
