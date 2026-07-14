"""Make episode_number NOT NULL with auto-increment per project

Renumbers any pre-existing duplicate (project_id, episode_number) rows (keeps
the earliest by created_at, moves later rows above the project max), backfills
NULL episode_number values with sequential numbers per project (ordered by
created_at ASC), then enforces NOT NULL and a unique constraint on
(project_id, episode_number) to guarantee ordering integrity.

Lock-safety (issue #318): NOT NULL is applied via CHECK ... NOT VALID ->
VALIDATE -> SET NOT NULL (PostgreSQL 12+ uses the validated check to skip the
full-table scan under ACCESS EXCLUSIVE), and both indexes build CONCURRENTLY
in an autocommit block so writes are never blocked on large tables.

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

	# Step 0: Fail loudly if this migration is run under a role subject to RLS
	# (issue #301). 003 applies FORCE ROW LEVEL SECURITY to episodes; under an
	# RLS-subject role the data repair below silently matches zero rows, then
	# the NOT NULL / unique constraints build over un-repaired data. With
	# row_security=off, a no-bypass role errors here instead of corrupting data;
	# for a superuser/BYPASSRLS migration role this is a harmless no-op.
	connection.execute(text("SET LOCAL row_security = off"))

	# Step 1: Renumber pre-existing duplicate (project_id, episode_number)
	# rows so the unique constraint below can never abort (issue #318).
	# Within each duplicate group the earliest row (created_at, id) keeps its
	# number; later rows move to sequential numbers above the project's
	# current max. (CTEs are evaluated against the pre-UPDATE snapshot, so
	# project_max reads the pre-dedupe max — renumbered values land strictly
	# above every pre-existing number and cannot collide.)
	dedupe_sql = text("""
	WITH ranked AS (
		SELECT
			id,
			project_id,
			created_at,
			ROW_NUMBER() OVER (
				PARTITION BY project_id, episode_number
				ORDER BY created_at ASC, id ASC
			) AS dup_rank
		FROM episodes
		WHERE episode_number IS NOT NULL
	),
	to_renumber AS (
		SELECT
			id,
			project_id,
			ROW_NUMBER() OVER (
				PARTITION BY project_id ORDER BY created_at ASC, id ASC
			) AS seq
		FROM ranked
		WHERE dup_rank > 1
	),
	project_max AS (
		SELECT project_id, MAX(episode_number) AS max_num
		FROM episodes
		WHERE episode_number IS NOT NULL
		GROUP BY project_id
	)
	UPDATE episodes e
	SET episode_number = pm.max_num + tr.seq
	FROM to_renumber tr
	JOIN project_max pm ON pm.project_id = tr.project_id
	WHERE e.id = tr.id
	""")
	connection.execute(dedupe_sql)

	# Step 2: Backfill NULL episode_numbers.
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

	# Step 3: Enforce NOT NULL without a full-table scan under ACCESS
	# EXCLUSIVE. The NOT VALID add is a brief lock; the scan happens in
	# VALIDATE (SHARE UPDATE EXCLUSIVE — writes continue); SET NOT NULL then
	# reuses the validated check (PostgreSQL 12+) instead of rescanning.
	# The DROP guard makes reruns safe: everything up to here commits when
	# the autocommit block below opens, so a failure later in this migration
	# would otherwise leave the check constraint behind and abort the re-add.
	op.execute(
		"ALTER TABLE episodes DROP CONSTRAINT IF EXISTS "
		"ck_episodes_episode_number_not_null"
	)
	op.execute(
		"ALTER TABLE episodes ADD CONSTRAINT ck_episodes_episode_number_not_null "
		"CHECK (episode_number IS NOT NULL) NOT VALID"
	)

	# Steps 4-5 run outside the migration transaction: VALIDATE only avoids
	# blocking writes when the NOT VALID add has already committed, and
	# CREATE INDEX CONCURRENTLY refuses to run inside a transaction at all.
	with op.get_context().autocommit_block():
		op.execute(
			"ALTER TABLE episodes VALIDATE CONSTRAINT "
			"ck_episodes_episode_number_not_null"
		)
		op.execute(
			"ALTER TABLE episodes ALTER COLUMN episode_number SET NOT NULL"
		)
		op.execute(
			"ALTER TABLE episodes DROP CONSTRAINT "
			"ck_episodes_episode_number_not_null"
		)

		# Step 4: Unique constraint per project, built without blocking
		# writes: CONCURRENTLY index first, then attach it as the constraint.
		# The DROP guards make reruns safe across BOTH failure windows: the
		# constraint drop (which takes its owned index with it) covers a
		# failure after ADD CONSTRAINT committed, and the index drop covers
		# the INVALID index a failed CONCURRENTLY build leaves behind.
		op.execute(
			"ALTER TABLE episodes DROP CONSTRAINT IF EXISTS "
			"uq_episodes_project_number"
		)
		op.execute("DROP INDEX IF EXISTS uq_episodes_project_number")
		op.execute(
			"CREATE UNIQUE INDEX CONCURRENTLY uq_episodes_project_number "
			"ON episodes (project_id, episode_number)"
		)
		op.execute(
			"ALTER TABLE episodes ADD CONSTRAINT uq_episodes_project_number "
			"UNIQUE USING INDEX uq_episodes_project_number"
		)

		# Step 5: Composite index for efficient ordering queries.
		op.execute("DROP INDEX IF EXISTS idx_episodes_project_number")
		op.create_index(
			'idx_episodes_project_number',
			'episodes',
			['project_id', 'episode_number'],
			postgresql_concurrently=True,
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
