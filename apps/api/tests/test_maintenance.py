"""
Unit tests for the stuck-episode reaper (issue #294).

The reaper uses a sync Celery session (SyncSessionLocal), which is independent of
the async test-DB transaction, so — following the existing Celery test convention
— the session is mocked and the reaper's selection/marking logic is exercised
directly.
"""
import uuid
from unittest.mock import MagicMock, patch


def _session_yielding_ids(ids):
    """Mock a SyncSessionLocal context manager whose query returns ``ids``."""
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = ids
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def test_reaper_marks_stuck_episodes_failed():
    from src.tasks import maintenance

    stuck_ids = [uuid.uuid4(), uuid.uuid4()]
    session = _session_yielding_ids(stuck_ids)
    with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
         patch("src.tasks.maintenance._update_episode", return_value=True) as mock_upd:
        count = maintenance.reap_stuck_episodes.run()

    assert count == 2
    assert mock_upd.call_count == 2
    assert mock_upd.call_args.kwargs["updates"]["generation_status"] == "failed"


def test_reaper_noop_when_nothing_stuck():
    from src.tasks import maintenance

    session = _session_yielding_ids([])
    with patch("src.tasks.maintenance.SyncSessionLocal", return_value=session), \
         patch("src.tasks.maintenance._update_episode") as mock_upd:
        count = maintenance.reap_stuck_episodes.run()

    assert count == 0
    mock_upd.assert_not_called()


def test_reaper_only_targets_non_terminal_statuses():
    """Terminal/never-started statuses must not be in the reap set."""
    from src.tasks.maintenance import NON_TERMINAL_STATUSES

    assert "draft" not in NON_TERMINAL_STATUSES
    assert "complete" not in NON_TERMINAL_STATUSES
    assert "failed" not in NON_TERMINAL_STATUSES
    assert "queued" in NON_TERMINAL_STATUSES
    assert "generating" in NON_TERMINAL_STATUSES
