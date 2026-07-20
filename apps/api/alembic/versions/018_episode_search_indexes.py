"""Add episode search indexes: pg_trgm GIN on title/description + btree on created_at

Episode search (episode_service.list_episodes) filters titles/descriptions with a
leading-wildcard ILIKE on episode_metadata->>'title' and ->>'description', and
filters/sorts by created_at — all unindexed, so large tenants hit sequential
scans (issue #322).

This migration adds:
- the pg_trgm extension (provides the gin_trgm_ops operator class)
- GIN gin_trgm_ops expression indexes on (episode_metadata->>'title') and
  (episode_metadata->>'description') so substring/ILIKE (incl. leading wildcard)
  can use an index instead of a sequential scan
- a btree index on created_at for the range filters and ordering

pg_trgm preserves the exact current substring-match semantics (unlike full-text
search, which would change tokenization/ranking and API-visible results).

`episodes` pre-exists and may hold data, so every index is built CONCURRENTLY
inside an autocommit block (issue #318) — the build never takes a write-blocking
lock. A DROP INDEX IF EXISTS guard precedes each create so a rerun is safe after
a failed CONCURRENTLY build (which leaves an INVALID index behind).

Revision ID: 018
Revises: 017
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TITLE_INDEX = "idx_episodes_metadata_title_trgm"
DESCRIPTION_INDEX = "idx_episodes_metadata_description_trgm"
CREATED_AT_INDEX = "idx_episodes_created_at"


def upgrade() -> None:
	# gin_trgm_ops lets a GIN index serve substring/ILIKE matches, including the
	# leading-wildcard patterns the episode search uses.
	op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

	# Build CONCURRENTLY in an autocommit block so the build never blocks writes
	# on the populated episodes table (issue #318). DROP IF EXISTS makes reruns
	# safe after a failed CONCURRENTLY build (leaves an INVALID index behind).
	with op.get_context().autocommit_block():
		op.execute(f"DROP INDEX IF EXISTS {TITLE_INDEX}")
		op.execute(
			f"CREATE INDEX CONCURRENTLY {TITLE_INDEX} "
			f"ON episodes USING gin ((episode_metadata->>'title') gin_trgm_ops)"
		)

		op.execute(f"DROP INDEX IF EXISTS {DESCRIPTION_INDEX}")
		op.execute(
			f"CREATE INDEX CONCURRENTLY {DESCRIPTION_INDEX} "
			f"ON episodes USING gin ((episode_metadata->>'description') gin_trgm_ops)"
		)

		op.execute(f"DROP INDEX IF EXISTS {CREATED_AT_INDEX}")
		op.execute(
			f"CREATE INDEX CONCURRENTLY {CREATED_AT_INDEX} "
			f"ON episodes USING btree (created_at)"
		)


def downgrade() -> None:
	# Plain DROP INDEX (brief ACCESS EXCLUSIVE lock) is acceptable in a
	# downgrade; IF EXISTS keeps it idempotent. pg_trgm is left installed — other
	# objects may come to depend on it and dropping a shared extension is unsafe.
	op.execute(f"DROP INDEX IF EXISTS {CREATED_AT_INDEX}")
	op.execute(f"DROP INDEX IF EXISTS {DESCRIPTION_INDEX}")
	op.execute(f"DROP INDEX IF EXISTS {TITLE_INDEX}")
