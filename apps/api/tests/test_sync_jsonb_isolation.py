"""
Regression test for issue #372.

The mocked-podcastfy workflow tests used ``patch.dict(sys.modules, {...})``,
whose exit path clears ``sys.modules`` and re-applies a snapshot — evicting
every module imported *during* the patch window. The first such test lazily
imported the whole ``psycopg`` tree inside the window; eviction + re-import
produced a fresh ``Jsonb`` class unknown to the already-registered adapter
map, so any later sync-session ORM insert with a JSONB column failed with
``cannot adapt type 'Jsonb'``.

This file sorts after ``tests/test_celery_workflow.py`` so, in a shared
pytest session (including the full suite), the insert below exercises the
exact poisoned path from the issue repro.
"""
import uuid

from src.database import SyncSessionLocal
from src.models.user import User


def test_sync_orm_jsonb_insert_after_workflow_tests():
    with SyncSessionLocal() as db:
        user = User(
            email=f"jsonb-isolation-{uuid.uuid4()}@test.local",
            password_hash="x",
            tenant_id=uuid.uuid4(),
            encrypted_api_keys={"probe": "value"},
        )
        db.add(user)
        db.flush()  # executes the INSERT (where Jsonb adaptation happens)
        db.rollback()  # leave no row behind
