"""Tests for the generate_podcast_task idempotency guard (issue #295).

The root task runs paid LLM/TTS work. Under at-least-once delivery a worker loss
(OOM/deploy/SIGKILL) would re-queue and re-run the whole paid pipeline. The guard
must: (1) make the task fail-fast (acks_late=False), (2) short-circuit
already-complete or in-flight episodes before any paid call, and (3) use a Redis
lock to block concurrent/duplicate in-flight runs while self-healing via TTL.
"""

import sys
import types
from unittest.mock import MagicMock, create_autospec, patch
from uuid import uuid4

from podcastfy.client import generate_podcast as real_generate_podcast

from src.tasks import idempotency
from src.tasks.podcast_generation import generate_podcast_task


# ---------------------------------------------------------------------------
# Phase 1: fail-fast decorator config
# ---------------------------------------------------------------------------

def test_root_task_overrides_acks_late_false():
    """The expensive root task must ack early so abrupt loss is not redelivered."""
    assert generate_podcast_task.acks_late is False


def test_root_task_overrides_reject_on_worker_lost_false():
    """Worker-lost must not re-queue the paid task."""
    assert generate_podcast_task.reject_on_worker_lost is False


# ---------------------------------------------------------------------------
# Phase 2: Redis lock helper
# ---------------------------------------------------------------------------

def test_acquire_returns_true_on_fresh_key():
    """A fresh SET NX succeeds → lock acquired."""
    client = MagicMock()
    client.set.return_value = True
    with patch.object(idempotency, "_redis", return_value=client):
        assert idempotency.acquire_generation_lock("ep1", "task-a") is True
    # NX + EX must both be set
    _, kwargs = client.set.call_args
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") and kwargs["ex"] > idempotency.settings.CELERY_TASK_TIME_LIMIT


def test_acquire_false_when_held_by_other_task():
    """If the key is held by a different task, acquisition fails (concurrent dup)."""
    client = MagicMock()
    client.set.return_value = None
    client.get.return_value = "task-other"
    with patch.object(idempotency, "_redis", return_value=client):
        assert idempotency.acquire_generation_lock("ep1", "task-a") is False


def test_acquire_reentrant_for_same_task():
    """A Celery retry keeps the same task_id → re-acquiring our own lock succeeds."""
    client = MagicMock()
    client.set.return_value = None
    client.get.return_value = "task-a"
    with patch.object(idempotency, "_redis", return_value=client):
        assert idempotency.acquire_generation_lock("ep1", "task-a") is True


def test_acquire_fails_open_on_redis_error():
    """A Redis outage must never permanently block generation (fail-open)."""
    client = MagicMock()
    client.set.side_effect = ConnectionError("redis down")
    with patch.object(idempotency, "_redis", return_value=client):
        assert idempotency.acquire_generation_lock("ep1", "task-a") is True


def test_release_compare_and_deletes_atomically():
    """Release runs a compare-and-delete so a lock re-acquired by a later run is safe."""
    client = MagicMock()
    with patch.object(idempotency, "_redis", return_value=client):
        idempotency.release_generation_lock("ep1", "task-a")
    client.eval.assert_called_once()
    args = client.eval.call_args.args
    # KEYS[1] = lock key, ARGV[1] = owning task id
    assert "ep1" in args[2]
    assert args[3] == "task-a"


def test_release_fails_open_on_redis_error():
    """A Redis error during release is swallowed (never raises)."""
    client = MagicMock()
    client.eval.side_effect = ConnectionError("redis down")
    with patch.object(idempotency, "_redis", return_value=client):
        idempotency.release_generation_lock("ep1", "task-a")  # must not raise


# ---------------------------------------------------------------------------
# Phase 3: entry guard short-circuits before any paid work
# ---------------------------------------------------------------------------

def _mock_podcastfy(return_value="/tmp/out.mp3"):
    mock_client = MagicMock()
    mock_client.generate_podcast = create_autospec(
        real_generate_podcast, return_value=return_value
    )
    mod = types.ModuleType("podcastfy")
    mod.client = mock_client
    return mock_client, {"podcastfy": mod, "podcastfy.client": mock_client}


def _run_with_status(status, *, retries=0, acquire=True):
    """Run the task with a stubbed DB status / lock and return (result, mock_gen)."""
    mock_client, mock_modules = _mock_podcastfy()
    mock_gen = mock_client.generate_podcast

    audio = MagicMock()
    audio.__len__ = MagicMock(return_value=60000)

    generate_podcast_task.push_request(id="task-a", retries=retries)
    try:
        with patch.object(generate_podcast_task, "update_state"), \
             patch("src.tasks.podcast_generation._load_generation_status", return_value=status), \
             patch("src.tasks.podcast_generation.acquire_generation_lock", return_value=acquire), \
             patch("src.tasks.podcast_generation.release_generation_lock"), \
             patch("src.tasks.podcast_generation._update_episode"), \
             patch.dict(sys.modules, mock_modules), \
             patch("src.tasks.podcast_generation.os.path.getsize", return_value=1024), \
             patch("src.tasks.podcast_generation.AudioSegment") as mock_audio, \
             patch("src.tasks.podcast_generation.finalize_episode_generation_task"):
            mock_audio.from_file.return_value = audio
            result = generate_podcast_task.run(episode_id=str(uuid4()), urls=["https://x.com"])
    finally:
        generate_podcast_task.pop_request()
    return result, mock_gen


def test_complete_episode_short_circuits_without_paid_work():
    """A 'complete' episode must return early and never call generate_podcast()."""
    result, mock_gen = _run_with_status("complete")
    mock_gen.assert_not_called()
    assert result["status"] in ("skipped", "success")
    assert result.get("skipped") is True


def test_in_progress_episode_short_circuits_as_duplicate():
    """An in-flight status (e.g. 'generating') is a redelivered duplicate → skip."""
    result, mock_gen = _run_with_status("generating")
    mock_gen.assert_not_called()
    assert result.get("skipped") is True


def test_held_lock_short_circuits_as_concurrent_duplicate():
    """If the Redis lock is already held, skip without running paid work."""
    result, mock_gen = _run_with_status("queued", acquire=False)
    mock_gen.assert_not_called()
    assert result.get("skipped") is True


def test_queued_episode_proceeds():
    """A normal 'queued' episode runs the paid pipeline."""
    result, mock_gen = _run_with_status("queued")
    mock_gen.assert_called_once()
    assert result["status"] == "success"


def test_retry_of_in_progress_run_proceeds():
    """A Celery retry (same task_id, status now 'generating') must NOT short-circuit."""
    result, mock_gen = _run_with_status("generating", retries=1)
    mock_gen.assert_called_once()
    assert result["status"] == "success"
