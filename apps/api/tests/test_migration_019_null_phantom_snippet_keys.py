"""Migration 019: null the phantom audio_snippets.s3_key values written before #536 (#537).

Runs the migration's real SQL against the real database (superuser connection,
one transaction, rolled back at the end) through alembic's own Operations, so
it is the shipped statements that are proven, not a recording of them.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from src.database import SyncSessionLocal

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "019_null_phantom_snippet_keys.py"


def _migration():
    spec = importlib.util.spec_from_file_location("migration_019", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chains_after_018():
    module = _migration()
    assert (module.revision, module.down_revision) == ("019", "018")


@pytest.fixture
def connection():
    """A superuser connection in a transaction that is always rolled back."""
    with SyncSessionLocal() as session:
        engine = session.get_bind()
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


def _seed(conn):
    tenant = uuid.uuid4()
    user = uuid.uuid4()
    conn.execute(sa.text(
        "INSERT INTO users (id, email, password_hash, tenant_id, created_at, updated_at) "
        "VALUES (:id, :email, 'x', :tenant, now(), now())"
    ), {"id": user, "email": f"m019-{user}@test.local", "tenant": tenant})
    keys = {name: f"snippets/user-{user}/{name}.mp3" for name in ("phantom", "real", "other")}

    def snippet(name, s3_url):
        conn.execute(sa.text(
            "INSERT INTO audio_snippets (id, user_id, tenant_id, name, snippet_type, file_path, s3_key, s3_url, created_at, updated_at) "
            "VALUES (:id, :user, :tenant, :name, 'intro', '/tmp/x.mp3', :key, :url, now(), now())"
        ), {"id": uuid.uuid4(), "user": user, "tenant": tenant, "name": name, "key": keys[name], "url": s3_url})

    snippet("phantom", None)  # a key was written, nothing was uploaded
    snippet("real", f"https://bucket.s3.amazonaws.com/{keys['real']}")
    for name in ("phantom", "other"):
        conn.execute(sa.text(
            "INSERT INTO storage_deletion_outbox (id, s3_key, attempts, created_at) VALUES (:id, :key, 3, now())"
        ), {"id": uuid.uuid4(), "key": keys[name]})
    return keys


def _upgrade(conn):
    with Operations.context(MigrationContext.configure(conn)):
        _migration().upgrade()


def _snippet_key(conn, name):
    return conn.execute(sa.text("SELECT s3_key FROM audio_snippets WHERE name = :n AND file_path = '/tmp/x.mp3' ORDER BY created_at DESC LIMIT 1"), {"n": name}).scalar()


def _queued(conn, key):
    return conn.execute(sa.text("SELECT count(*) FROM storage_deletion_outbox WHERE s3_key = :k"), {"k": key}).scalar()


def test_phantom_keys_are_nulled_and_their_queued_deletions_dropped(connection):
    keys = _seed(connection)

    _upgrade(connection)

    assert _snippet_key(connection, "phantom") is None
    assert _snippet_key(connection, "real") == keys["real"]  # a real upload keeps its key
    assert _queued(connection, keys["phantom"]) == 0  # the undrainable row is gone
    assert _queued(connection, keys["other"]) == 1  # unrelated queued deletions stay


def test_a_rerun_changes_nothing(connection):
    keys = _seed(connection)
    _upgrade(connection)

    _upgrade(connection)

    assert _snippet_key(connection, "real") == keys["real"]
    assert _queued(connection, keys["other"]) == 1


def test_a_queued_deletion_whose_snippet_is_gone_is_left_queued(connection):
    """Deletion and erasure delete the snippet in the transaction that queues
    its key, so such a key can no longer be told phantom from real. Dropping it
    could orphan a real object during an S3 outage, so it stays queued (with a
    bucket it drains on its own: S3 DeleteObject on a missing key succeeds)."""
    keys = _seed(connection)
    orphan = keys["phantom"].replace("phantom", "deleted-snippet")
    connection.execute(sa.text(
        "INSERT INTO storage_deletion_outbox (id, s3_key, attempts, created_at) VALUES (:id, :key, 3, now())"
    ), {"id": uuid.uuid4(), "key": orphan})

    _upgrade(connection)

    assert _queued(connection, orphan) == 1
