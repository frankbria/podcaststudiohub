"""
Unit tests for podcast generation success callback.

Tests that on_generation_success persists audio file metadata
to the Episode model in the database.
"""
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_success_result(
    audio_file_path="/data/audio/ep123.mp3",
    transcript_path="/data/audio/ep123_transcript.txt",
    duration_seconds=300.5,
    file_size_bytes=5_242_880,
):
    """Return a typical 'success' result dict from generate_podcast_task."""
    return {
        "status": "success",
        "audio_file_path": audio_file_path,
        "transcript_path": transcript_path,
        "duration_seconds": duration_seconds,
        "file_size_bytes": file_size_bytes,
        "error": None,
    }


def _make_episode(episode_id="episode-uuid-1234"):
    """Create a mock Episode object."""
    episode = MagicMock()
    episode.id = episode_id
    episode.generation_status = "generating"
    episode.generation_progress = {}
    episode.file_path = None
    episode.transcript_path = None
    episode.duration_seconds = None
    episode.file_size_bytes = None
    return episode


# ---------------------------------------------------------------------------
# Tests for on_generation_success callback
# ---------------------------------------------------------------------------

class TestOnGenerationSuccess:
    """Tests for the on_generation_success Celery callback."""

    def _run_callback(self, result, episode_id, mock_episode=None):
        """Helper: run the callback with mocked DB session."""
        from src.tasks.podcast_generation import on_generation_success

        if mock_episode is None:
            mock_episode = _make_episode(episode_id)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_episode

        with patch("src.tasks.podcast_generation.SessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            on_generation_success(result, "task-id-abc", [], {"episode_id": episode_id})

        return mock_episode, mock_db

    def test_file_path_is_persisted(self):
        """file_path on the Episode is set from result['audio_file_path']."""
        result = _make_success_result(audio_file_path="/data/audio/ep1.mp3")
        episode, _ = self._run_callback(result, "ep-1")

        assert episode.file_path == "/data/audio/ep1.mp3"

    def test_transcript_path_is_persisted(self):
        """transcript_path on the Episode is set from result['transcript_path']."""
        result = _make_success_result(transcript_path="/data/audio/ep1_transcript.txt")
        episode, _ = self._run_callback(result, "ep-1")

        assert episode.transcript_path == "/data/audio/ep1_transcript.txt"

    def test_duration_seconds_is_persisted(self):
        """duration_seconds on the Episode is set from result['duration_seconds']."""
        result = _make_success_result(duration_seconds=420.75)
        episode, _ = self._run_callback(result, "ep-1")

        assert episode.duration_seconds == 420.75

    def test_file_size_bytes_is_persisted(self):
        """file_size_bytes on the Episode is set from result['file_size_bytes']."""
        result = _make_success_result(file_size_bytes=10_000_000)
        episode, _ = self._run_callback(result, "ep-1")

        assert episode.file_size_bytes == 10_000_000

    def test_generation_status_set_to_complete(self):
        """generation_status on the Episode is set to 'complete'."""
        result = _make_success_result()
        episode, _ = self._run_callback(result, "ep-1")

        assert episode.generation_status == "complete"

    def test_generation_progress_updated_with_completion_info(self):
        """generation_progress is updated to reflect completion."""
        result = _make_success_result()
        episode, _ = self._run_callback(result, "ep-1")

        progress = episode.generation_progress
        assert progress.get("stage") == "complete"
        assert progress.get("progress") == 100
        assert "completed_at" in progress

    def test_db_commit_is_called(self):
        """Database session is committed after updating the episode."""
        result = _make_success_result()
        _, mock_db = self._run_callback(result, "ep-1")

        mock_db.commit.assert_called_once()

    def test_failed_result_does_not_update_file_paths(self):
        """When result status is 'failed', file_path stays NULL."""
        from src.tasks.podcast_generation import on_generation_success

        failed_result = {
            "status": "failed",
            "audio_file_path": None,
            "transcript_path": None,
            "duration_seconds": 0,
            "file_size_bytes": 0,
            "error": "Something went wrong",
        }
        episode = _make_episode("ep-fail")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = episode

        with patch("src.tasks.podcast_generation.SessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            on_generation_success(failed_result, "task-id-abc", [], {"episode_id": "ep-fail"})

        # File path should NOT be set on failed results
        assert episode.file_path is None
        assert episode.generation_status != "complete"
        mock_db.commit.assert_not_called()

    def test_missing_episode_does_not_raise(self):
        """If episode is not found in DB, callback logs warning and returns gracefully."""
        from src.tasks.podcast_generation import on_generation_success

        result = _make_success_result()
        mock_db = MagicMock()
        # Simulate episode not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("src.tasks.podcast_generation.SessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should not raise any exception
            on_generation_success(result, "task-id-abc", [], {"episode_id": "nonexistent-id"})

        # DB should not be committed when episode not found
        mock_db.commit.assert_not_called()

    def test_missing_episode_id_in_kwargs_does_not_raise(self):
        """If episode_id is missing from kwargs, callback returns gracefully."""
        from src.tasks.podcast_generation import on_generation_success

        result = _make_success_result()

        with patch("src.tasks.podcast_generation.SessionLocal"):
            # Should not raise any exception
            on_generation_success(result, "task-id-abc", [], {})

    def test_db_commit_failure_does_not_raise(self):
        """If DB commit fails, callback logs error but does not re-raise."""
        from src.tasks.podcast_generation import on_generation_success

        result = _make_success_result()
        episode = _make_episode("ep-1")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = episode
        mock_db.commit.side_effect = Exception("DB connection lost")

        with patch("src.tasks.podcast_generation.SessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            # Should not raise — callback logs error instead
            on_generation_success(result, "task-id-abc", [], {"episode_id": "ep-1"})

    def test_episode_queried_by_episode_id(self):
        """The Episode is looked up using the episode_id from kwargs."""
        from src.tasks.podcast_generation import on_generation_success

        result = _make_success_result()
        mock_db = MagicMock()
        episode = _make_episode("ep-xyz")
        mock_db.query.return_value.filter.return_value.first.return_value = episode

        with patch("src.tasks.podcast_generation.SessionLocal") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            on_generation_success(result, "task-id-abc", [], {"episode_id": "ep-xyz"})

        # Verify Episode model was queried
        from src.models.episode import Episode
        mock_db.query.assert_called_once_with(Episode)


# ---------------------------------------------------------------------------
# Tests for PodcastGenerationTask class (callback registration)
# ---------------------------------------------------------------------------

class TestPodcastGenerationTaskCallback:
    """Tests for the custom Task class that registers on_success callback."""

    def test_task_has_on_success_method(self):
        """The generate_podcast_task has an on_success method defined."""
        from src.tasks.podcast_generation import generate_podcast_task
        assert hasattr(generate_podcast_task, "on_success")

    def test_on_success_calls_callback_function(self):
        """on_success method delegates to on_generation_success."""
        from src.tasks.podcast_generation import generate_podcast_task

        result = _make_success_result()
        with patch("src.tasks.podcast_generation.on_generation_success") as mock_cb:
            generate_podcast_task.on_success(result, "task-id", [], {"episode_id": "ep-1"})
            mock_cb.assert_called_once_with(result, "task-id", [], {"episode_id": "ep-1"})
