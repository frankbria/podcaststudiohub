"""
Regression test for issue #312 (found while demoing the idempotency fix).

Migration 001's episodes_status_check allowed only a subset of the
generation_status values the workflow actually writes. Statuses like
'distributing' (on_distribution_complete / record_platform_distribution),
'composing', 'uploading', and 'distribution_failed' (on_workflow_complete)
raised CheckViolation on commit — which the callbacks swallow, so per-platform
distribution results were silently never recorded. Migration 016 expands the
constraint; this test reads the live constraint definition so it can never
drift behind the code again.

The check is asserted against pg_constraint (SELECT-only) rather than by
committing rows: full-suite runs currently poison psycopg's Jsonb adaptation
for sync ORM inserts (see issue filed from #312 work), and an IN-list CHECK
needs no row-level exercise beyond its definition.
"""
from sqlalchemy import text

from src.database import SyncSessionLocal

# Every value assigned to Episode.generation_status anywhere in src/.
CODE_WRITTEN_STATUSES = [
    "draft",
    "queued",
    "extracting",
    "generating",
    "synthesizing",
    "composing",
    "uploading",
    "distributing",
    "distribution_failed",
    "complete",
    "failed",
]


def test_status_check_constraint_allows_all_code_written_statuses():
    with SyncSessionLocal() as db:
        condef = db.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'episodes_status_check' "
                "AND conrelid = 'episodes'::regclass"
            )
        ).scalar_one()

    for status in CODE_WRITTEN_STATUSES:
        assert f"'{status}'" in condef, (
            f"generation_status '{status}' is written by src/ but rejected by "
            f"episodes_status_check: {condef}"
        )
