"""
Tests for S3 upload workflow: upload_to_s3_task and finalize_episode_generation_task.

Uses unittest.mock to avoid requiring real AWS credentials or a running database.
Tests invoke the underlying task logic by calling the task's __wrapped__ function
or by configuring Celery eager mode.
"""
import uuid
from unittest.mock import MagicMock, patch


# ============================================================================
# Helpers
# ============================================================================

def _make_mock_episode(episode_id: str, user_id: str = None) -> MagicMock:
    """Create a mock Episode with required attributes."""
    episode = MagicMock()
    episode.id = uuid.UUID(episode_id)
    episode.user_id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    episode.generation_status = "generating"
    episode.generation_progress = {}
    episode.file_path = None
    episode.s3_url = None
    episode.s3_key = None
    episode.duration_seconds = None
    episode.file_size_bytes = None
    episode.transcript_path = None
    return episode


def _make_mock_celery_self():
    """Create a properly-configured mock Celery task self."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id-" + str(uuid.uuid4())
    mock_self.update_state = MagicMock()
    return mock_self


def _invoke_task(task, **kwargs):
    """
    Invoke a Celery bind=True task directly, bypassing Celery routing/retry machinery.

    For bind=True tasks, task.run is a bound method where self=task (the task instance).
    We set a fake request ID and mock update_state so the task can execute without
    a real Celery broker or worker context.
    """
    # Set a valid task request ID (required for Celery's update_state validation)
    task.request.update(id="test-task-id-" + str(uuid.uuid4()))

    with patch.object(task, 'update_state', MagicMock()):
        # task.run(**kwargs) - self is already bound to the task instance
        return task.run(**kwargs)


# ============================================================================
# upload_to_s3_task unit tests
# ============================================================================

class TestUploadToS3Task:
    """Unit tests for upload_to_s3_task."""

    def _invoke_upload(self, **kwargs):
        """Invoke upload_to_s3_task's underlying function with mocked self."""
        from src.tasks.s3_upload import upload_to_s3_task
        return _invoke_task(upload_to_s3_task, **kwargs)

    def test_s3_url_format_us_east_1(self):
        """S3 URL for us-east-1 uses legacy format without region subdomain."""
        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=1024),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_s3 = MagicMock()
            mock_boto.client.return_value = mock_s3

            result = self._invoke_upload(
                file_path="/tmp/audio.mp3",
                s3_key="podcasts/user-123/episode-456.mp3",
                bucket_name="test-bucket",
                content_type="audio/mpeg",
            )

        assert result["status"] == "success"
        assert result["s3_url"] == "https://test-bucket.s3.amazonaws.com/podcasts/user-123/episode-456.mp3"

    def test_s3_url_format_non_us_east_1(self):
        """S3 URL for other regions includes region subdomain."""
        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=1024),
        ):
            mock_settings.AWS_REGION = "eu-west-1"
            mock_s3 = MagicMock()
            mock_boto.client.return_value = mock_s3

            result = self._invoke_upload(
                file_path="/tmp/audio.mp3",
                s3_key="podcasts/user-123/episode-456.mp3",
                bucket_name="test-bucket",
                content_type="audio/mpeg",
            )

        assert result["status"] == "success"
        assert result["s3_url"] == "https://test-bucket.s3.eu-west-1.amazonaws.com/podcasts/user-123/episode-456.mp3"

    def test_upload_returns_correct_metadata(self):
        """upload_to_s3_task returns s3_key, s3_url, and file_size_bytes on success."""
        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=2048),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_boto.client.return_value = MagicMock()

            result = self._invoke_upload(
                file_path="/tmp/audio.mp3",
                s3_key="test/key.mp3",
                bucket_name="my-bucket",
            )

        assert result["status"] == "success"
        assert result["s3_key"] == "test/key.mp3"
        assert result["file_size_bytes"] == 2048
        assert result["error"] is None

    def test_upload_fails_gracefully_on_generic_exception(self):
        """upload_to_s3_task returns failed status when upload raises."""
        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_s3 = MagicMock()
            mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
            mock_boto.client.return_value = mock_s3

            result = self._invoke_upload(
                file_path="/tmp/audio.mp3",
                s3_key="test/key.mp3",
                bucket_name="my-bucket",
            )

        assert result["status"] == "failed"
        assert result["s3_url"] is None
        assert "Connection timeout" in result["error"]

    def test_upload_passes_content_type(self):
        """upload_to_s3_task passes content_type in ExtraArgs to S3."""
        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=100),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_s3 = MagicMock()
            mock_boto.client.return_value = mock_s3

            self._invoke_upload(
                file_path="/tmp/audio.mp3",
                s3_key="test/key.mp3",
                bucket_name="my-bucket",
                content_type="audio/mpeg",
            )

        # Verify the ExtraArgs was passed with content type
        upload_call = mock_s3.upload_file.call_args
        assert upload_call is not None
        assert upload_call.kwargs.get("ExtraArgs") == {"ContentType": "audio/mpeg"}


# ============================================================================
# finalize_episode_generation_task unit tests
# ============================================================================

class TestFinalizeEpisodeGenerationTask:
    """Unit tests for finalize_episode_generation_task."""

    def _make_generation_result(self, **overrides):
        result = {
            "status": "success",
            "audio_file_path": "/tmp/episode-abc.mp3",
            "transcript_path": "/tmp/episode-abc_transcript.txt",
            "duration_seconds": 300.0,
            "file_size_bytes": 5_000_000,
            "error": None,
        }
        result.update(overrides)
        return result

    def _invoke_finalize(self, episode_id, generation_result, mock_db):
        """Invoke finalize_episode_generation_task's underlying function."""
        from src.tasks.podcast_generation import finalize_episode_generation_task
        return _invoke_task(
            finalize_episode_generation_task,
            episode_id=episode_id,
            generation_result=generation_result,
        )

    def _make_db_context_manager(self, episode):
        """Create a mock database context manager."""
        mock_db = MagicMock()
        mock_db.get.return_value = episode
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.commit = MagicMock()
        return mock_db

    def test_skips_s3_upload_when_bucket_not_configured(self):
        """If AWS_S3_BUCKET is not set, episode is marked complete without S3 upload."""
        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)
        generation_result = self._make_generation_result()
        mock_db = self._make_db_context_manager(episode)

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
        ):
            mock_settings.AWS_S3_BUCKET = None
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "success"
        assert episode.generation_status == "complete"
        assert episode.s3_url is None
        assert episode.s3_key is None
        assert episode.file_path == "/tmp/episode-abc.mp3"

    def test_populates_s3_url_on_successful_upload(self):
        """Episode.s3_url and s3_key are populated after successful S3 upload."""
        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id, user_id)
        generation_result = self._make_generation_result()
        mock_db = self._make_db_context_manager(episode)

        expected_s3_key = f"podcasts/user-{user_id}/episode-{episode_id}.mp3"
        expected_s3_url = f"https://test-bucket.s3.amazonaws.com/{expected_s3_key}"
        mock_upload_result = {
            "status": "success",
            "s3_key": expected_s3_key,
            "s3_url": expected_s3_url,
            "file_size_bytes": 5_000_000,
            "error": None,
        }

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
            patch("src.tasks.podcast_generation.upload_to_s3_task", return_value=mock_upload_result),
        ):
            mock_settings.AWS_S3_BUCKET = "test-bucket"
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "success"
        assert episode.generation_status == "complete"
        assert episode.s3_url == expected_s3_url
        assert episode.s3_key == expected_s3_key
        assert episode.file_path == "/tmp/episode-abc.mp3"
        assert episode.duration_seconds == 300.0
        assert episode.file_size_bytes == 5_000_000

    def test_marks_failed_when_s3_upload_fails(self):
        """If S3 upload fails, episode.generation_status is set to 'failed'."""
        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id, user_id)
        generation_result = self._make_generation_result()
        mock_db = self._make_db_context_manager(episode)

        mock_upload_result = {
            "status": "failed",
            "s3_key": None,
            "s3_url": None,
            "file_size_bytes": 0,
            "error": "S3 bucket does not exist",
        }

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
            patch("src.tasks.podcast_generation.upload_to_s3_task", return_value=mock_upload_result),
        ):
            mock_settings.AWS_S3_BUCKET = "missing-bucket"
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "failed"
        assert episode.generation_status == "failed"

    def test_marks_failed_when_generation_failed(self):
        """If generate_podcast_task returned failure, episode is marked failed."""
        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)
        generation_result = {
            "status": "failed",
            "audio_file_path": None,
            "transcript_path": None,
            "duration_seconds": 0,
            "file_size_bytes": 0,
            "error": "LLM API error",
        }
        mock_db = self._make_db_context_manager(episode)

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
        ):
            mock_settings.AWS_S3_BUCKET = None
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "failed"
        assert episode.generation_status == "failed"

    def test_returns_failed_when_episode_not_found(self):
        """Returns failed status when episode_id doesn't match any Episode."""
        episode_id = str(uuid.uuid4())
        generation_result = self._make_generation_result()
        mock_db = self._make_db_context_manager(None)  # Episode not found

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
        ):
            mock_settings.AWS_S3_BUCKET = None
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "failed"
        assert "not found" in result["error"]

    def test_s3_key_naming_convention(self):
        """S3 key follows podcasts/user-{user_id}/episode-{episode_id}.mp3 format."""
        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id, user_id)
        generation_result = self._make_generation_result()
        mock_db = self._make_db_context_manager(episode)

        captured = {}

        def capture_upload(file_path, s3_key, bucket_name, content_type="audio/mpeg"):
            captured["s3_key"] = s3_key
            return {
                "status": "success",
                "s3_key": s3_key,
                "s3_url": f"https://{bucket_name}.s3.amazonaws.com/{s3_key}",
                "file_size_bytes": 500,
                "error": None,
            }

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
            patch("src.tasks.podcast_generation.upload_to_s3_task", side_effect=capture_upload),
        ):
            mock_settings.AWS_S3_BUCKET = "test-bucket"
            self._invoke_finalize(episode_id, generation_result, mock_db)

        expected_key = f"podcasts/user-{user_id}/episode-{episode_id}.mp3"
        assert captured.get("s3_key") == expected_key

    def test_episode_stores_file_metadata(self):
        """Episode stores file_path, duration_seconds, file_size_bytes regardless of S3."""
        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)
        generation_result = self._make_generation_result(
            audio_file_path="/tmp/my-podcast.mp3",
            transcript_path="/tmp/my-podcast_transcript.txt",
            duration_seconds=450.5,
            file_size_bytes=9_999_999,
        )
        mock_db = self._make_db_context_manager(episode)

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
        ):
            mock_settings.AWS_S3_BUCKET = None
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "success"
        assert episode.file_path == "/tmp/my-podcast.mp3"
        assert episode.transcript_path == "/tmp/my-podcast_transcript.txt"
        assert episode.duration_seconds == 450.5
        assert episode.file_size_bytes == 9_999_999

    def test_generation_status_transitions_with_s3(self):
        """Episode status transitions from 'uploading' to 'complete' when S3 upload succeeds."""
        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id, user_id)
        generation_result = self._make_generation_result()
        mock_db = self._make_db_context_manager(episode)

        status_history = []

        def track_status(*args, **kwargs):
            status_history.append(episode.generation_status)

        mock_db.commit.side_effect = track_status

        upload_result = {
            "status": "success",
            "s3_key": f"podcasts/user-{user_id}/episode-{episode_id}.mp3",
            "s3_url": "https://test-bucket.s3.amazonaws.com/test.mp3",
            "file_size_bytes": 1000,
            "error": None,
        }

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
            patch("src.tasks.podcast_generation.upload_to_s3_task", return_value=upload_result),
        ):
            mock_settings.AWS_S3_BUCKET = "test-bucket"
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "success"
        # The episode should have gone through 'uploading' then 'complete'
        assert "uploading" in status_history
        assert episode.generation_status == "complete"


# ============================================================================
# generate_podcast_task chains finalize task
# ============================================================================

class TestGeneratePodcastTaskChaining:
    """Tests verifying generate_podcast_task chains to finalize task."""

    def test_generate_calls_finalize_delay_on_success(self):
        """generate_podcast_task calls finalize_episode_generation_task.delay on success."""
        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/test_podcast.mp3"

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)  # 60 seconds

        with (
            patch("src.tasks.podcast_generation.finalize_episode_generation_task") as mock_finalize,
            patch("podcastfy.client.generate_podcast", return_value=mock_audio_path),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
        ):
            mock_audio_cls.from_file.return_value = mock_audio_segment

            from src.tasks.podcast_generation import generate_podcast_task
            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
            )

        assert result["status"] == "success"
        mock_finalize.delay.assert_called_once()
        kwargs = mock_finalize.delay.call_args.kwargs
        assert kwargs.get("episode_id") == episode_id
        assert kwargs.get("generation_result", {}).get("status") == "success"
