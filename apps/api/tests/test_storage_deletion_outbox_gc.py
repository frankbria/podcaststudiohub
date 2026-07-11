"""
Unit tests for the storage-deletion-outbox GC worker (issue #366).

Mirrors the reaper's test convention (tests/test_maintenance.py): the task
uses a sync Celery session (SyncSessionLocal) independent of the async test-DB
transaction, so the session and StorageService are mocked and the drain
task's batch/retry logic is exercised directly via ``.run()``.
"""
from unittest.mock import MagicMock, patch

import pytest


def _session_yielding_rows(rows):
	"""Mock a SyncSessionLocal context manager whose query returns ``rows``."""
	session = MagicMock()
	session.execute.return_value.scalars.return_value.all.return_value = rows
	session.__enter__ = MagicMock(return_value=session)
	session.__exit__ = MagicMock(return_value=False)
	return session


def _make_row(s3_key=None, file_path=None, attempts=0):
	row = MagicMock()
	row.s3_key = s3_key
	row.file_path = file_path
	row.attempts = attempts
	row.last_attempt_at = None
	return row


def test_drain_noop_when_empty():
	from src.tasks import maintenance

	session = _session_yielding_rows([])
	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 0
	session.commit.assert_not_called()


def test_drain_deletes_s3_key_and_removes_row():
	from src.tasks import maintenance

	row = _make_row(s3_key="podcasts/episode.mp3")
	session = _session_yielding_rows([row])
	mock_storage = MagicMock()

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
		patch("src.tasks.maintenance.StorageService", return_value=mock_storage), \
		patch("src.tasks.maintenance.asyncio.run") as mock_asyncio_run:
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 1
	mock_asyncio_run.assert_called_once()
	session.delete.assert_called_once_with(row)
	session.commit.assert_called_once()


def test_drain_removes_local_file_and_deletes_row(tmp_path):
	from src.tasks import maintenance

	target = tmp_path / "audio.mp3"
	target.write_bytes(b"AUDIO")
	row = _make_row(file_path=str(target))
	session = _session_yielding_rows([row])

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 1
	assert not target.exists()
	session.delete.assert_called_once_with(row)


def test_drain_treats_missing_local_file_as_success():
	"""A local file that's already gone is not an error — delete_object-style
	idempotency for the filesystem path (issue #366, AC5)."""
	from src.tasks import maintenance

	row = _make_row(file_path="/nonexistent/path/does-not-exist.mp3")
	session = _session_yielding_rows([row])

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 1
	session.delete.assert_called_once_with(row)


def test_drain_increments_attempts_on_s3_failure():
	from src.tasks import maintenance

	row = _make_row(s3_key="podcasts/episode.mp3", attempts=2)
	session = _session_yielding_rows([row])
	mock_storage = MagicMock()

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
		patch("src.tasks.maintenance.StorageService", return_value=mock_storage), \
		patch("src.tasks.maintenance.asyncio.run", side_effect=Exception("S3 unavailable")):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 0
	session.delete.assert_not_called()
	assert row.attempts == 3
	assert row.last_attempt_at is not None
	session.commit.assert_called_once()


def test_drain_increments_attempts_on_local_delete_failure():
	from src.tasks import maintenance

	row = _make_row(file_path="/some/path.mp3", attempts=0)
	session = _session_yielding_rows([row])

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
		patch("src.tasks.maintenance.os.remove", side_effect=PermissionError("locked")):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 0
	session.delete.assert_not_called()
	assert row.attempts == 1


def test_drain_only_touches_s3_when_local_delete_already_failed():
	"""A row with both s3_key and file_path must not be marked drained (row
	deleted) unless BOTH deletions succeeded."""
	from src.tasks import maintenance

	row = _make_row(s3_key="podcasts/episode.mp3", file_path="/some/path.mp3")
	session = _session_yielding_rows([row])
	mock_storage = MagicMock()

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
		patch("src.tasks.maintenance.StorageService", return_value=mock_storage), \
		patch("src.tasks.maintenance.asyncio.run"), \
		patch("src.tasks.maintenance.os.remove", side_effect=OSError("disk error")):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 0
	session.delete.assert_not_called()
	assert row.attempts == 1


def test_drain_loops_while_full_batch_processed():
	"""A backlog larger than one batch drains in a single invocation."""
	from src.tasks import maintenance

	batch_size = maintenance.STORAGE_GC_BATCH_SIZE
	full_batch = [_make_row(s3_key=f"key-{i}") for i in range(batch_size)]
	partial_batch = [_make_row(s3_key="key-last")]

	session1 = _session_yielding_rows(full_batch)
	session2 = _session_yielding_rows(partial_batch)
	session3 = _session_yielding_rows([])
	mock_storage = MagicMock()

	with patch(
		"src.tasks.maintenance.SyncSessionLocal",
		side_effect=[session1, session2, session3],
	), \
		patch("src.tasks.maintenance.StorageService", return_value=mock_storage), \
		patch("src.tasks.maintenance.asyncio.run"):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == batch_size + 1


def test_drain_stops_after_partial_batch():
	"""A batch smaller than the limit means the queue is empty — no extra
	round-trip to fetch a third (empty) batch."""
	from src.tasks import maintenance

	row = _make_row(s3_key="only-key")
	session = _session_yielding_rows([row])
	mock_storage = MagicMock()

	with patch(
		"src.tasks.maintenance.SyncSessionLocal", return_value=session
	) as mock_factory, \
		patch("src.tasks.maintenance.StorageService", return_value=mock_storage), \
		patch("src.tasks.maintenance.asyncio.run"):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 1
	assert mock_factory.call_count == 1


def test_drain_query_uses_skip_locked_order_by_created_at():
	"""The batch SELECT must use FOR UPDATE SKIP LOCKED ordered by created_at
	so concurrent drain invocations don't contend on the same rows."""
	from src.tasks import maintenance

	session = _session_yielding_rows([])
	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session):
		maintenance.drain_storage_deletion_outbox.run()

	from sqlalchemy.dialects import postgresql

	compiled_query = session.execute.call_args[0][0]
	sql = str(compiled_query.compile(
		dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
	))
	assert "SKIP LOCKED" in sql.upper()
	assert "ORDER BY" in sql.upper()


@pytest.mark.parametrize("registered_name", ["drain_storage_deletion_outbox"])
def test_drain_task_registered_on_callbacks_queue(registered_name):
	from src.worker import celery_app

	assert celery_app.conf.task_routes[registered_name]["queue"] == "callbacks"


def test_drain_task_has_beat_schedule_entry():
	from src.worker import celery_app

	assert "drain-storage-deletion-outbox" in celery_app.conf.beat_schedule
	entry = celery_app.conf.beat_schedule["drain-storage-deletion-outbox"]
	assert entry["task"] == "drain_storage_deletion_outbox"

def test_drain_stops_when_full_batch_makes_no_progress():
	"""A full batch where every deletion fails must terminate the drain loop
	instead of re-fetching the same failing rows until the task time limit
	kills it (e.g. an S3 outage during a large erasure) — the beat tick and
	the next delete flow's trigger retry later (#366)."""
	from src.tasks import maintenance

	rows = [
		_make_row(s3_key=f"podcasts/ep-{i}.mp3")
		for i in range(maintenance.STORAGE_GC_BATCH_SIZE)
	]
	session = _session_yielding_rows(rows)
	mock_storage = MagicMock()

	with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
		patch("src.tasks.maintenance.StorageService", return_value=mock_storage), \
		patch("src.tasks.maintenance.asyncio.run", side_effect=Exception("S3 down")):
		drained = maintenance.drain_storage_deletion_outbox.run()

	assert drained == 0
	# One fetch, then stop: zero progress on a full batch must not refetch.
	session.execute.assert_called_once()
	for row in rows:
		assert row.attempts == 1
