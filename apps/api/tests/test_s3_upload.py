"""
Tests for S3 upload workflow: upload_to_s3_task and finalize_episode_generation_task.

Uses unittest.mock to avoid requiring real AWS credentials or a running database.
Tests invoke the underlying task logic by calling the task's __wrapped__ function
or by configuring Celery eager mode.
"""
import os
import tempfile
import uuid
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from sqlalchemy.orm.exc import StaleDataError


# ============================================================================
# Helpers
# ============================================================================

def _make_mock_episode(episode_id: str, user_id: str = None) -> MagicMock:
    """Create a mock Episode with required attributes."""
    episode = MagicMock()
    episode.id = uuid.UUID(episode_id)
    episode.user_id = uuid.UUID(user_id) if user_id else uuid.uuid4()
    episode.tenant_id = uuid.uuid4()
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
        """upload_to_s3_task returns failed status after retries are exhausted."""
        from src.tasks.s3_upload import upload_to_s3_task

        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
            patch.object(
                upload_to_s3_task,
                "retry",
                side_effect=upload_to_s3_task.MaxRetriesExceededError(),
            ),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_s3 = MagicMock()
            mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
            mock_boto.client.return_value = mock_s3
            upload_to_s3_task.request.update(retries=3)

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

    def test_skips_s3_upload_when_bucket_not_configured(self, tmp_path):
        """If AWS_S3_BUCKET is not set, episode is marked complete and the audio is
        persisted off /tmp into LOCAL_AUDIO_STORAGE_PATH so it stays downloadable (#292)."""
        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)

        # Real source file so the no-S3 branch can copy it to persistent storage.
        src_audio = tmp_path / "episode-abc.mp3"
        src_audio.write_bytes(b"FAKE_MP3")
        storage_dir = tmp_path / "audio"
        generation_result = self._make_generation_result(audio_file_path=str(src_audio))
        mock_db = self._make_db_context_manager(episode)

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
        ):
            mock_settings.AWS_S3_BUCKET = None
            mock_settings.LOCAL_AUDIO_STORAGE_PATH = str(storage_dir)
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "success"
        assert episode.generation_status == "complete"
        assert episode.s3_url is None
        assert episode.s3_key is None
        # file_path now points into persistent storage, not the ephemeral source
        assert episode.file_path == str(storage_dir / f"episode-{episode_id}.mp3")
        assert os.path.isfile(episode.file_path)
        assert episode.file_path != str(src_audio)

    def test_no_s3_path_cleans_up_run_dir_after_persisting(self, tmp_path):
        """Issue #309: with no S3 bucket, once the audio is copied into persistent
        storage the per-run temp dir (audio + transcript) must be removed."""
        import shutil

        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)

        run_dir = tempfile.mkdtemp(prefix="podcastfy-run-")
        src_audio = os.path.join(run_dir, "podcast_abc.mp3")
        transcript = os.path.join(run_dir, "transcript_abc.txt")
        storage_dir = tmp_path / "audio"
        try:
            with open(src_audio, "wb") as f:
                f.write(b"FAKE_MP3")
            with open(transcript, "w") as f:
                f.write("transcript")
            generation_result = self._make_generation_result(
                audio_file_path=src_audio, transcript_path=None
            )
            mock_db = self._make_db_context_manager(episode)

            with (
                patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
                patch("src.tasks.podcast_generation.settings") as mock_settings,
            ):
                mock_settings.AWS_S3_BUCKET = None
                mock_settings.LOCAL_AUDIO_STORAGE_PATH = str(storage_dir)
                result = self._invoke_finalize(episode_id, generation_result, mock_db)

            assert result["status"] == "success"
            assert episode.generation_status == "complete"
            assert os.path.isfile(episode.file_path)
            assert not os.path.exists(run_dir), (
                "run dir should be removed once the persistent copy exists"
            )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

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
            patch("src.tasks.podcast_generation.upload_to_s3_task", return_value=mock_upload_result) as mock_upload,
            patch("src.tasks.podcast_generation.time.sleep") as mock_sleep,
        ):
            mock_settings.AWS_S3_BUCKET = "missing-bucket"
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "failed"
        assert episode.generation_status == "failed"
        # Inline upload now retries (issue #220): exhausts 3 attempts before failing.
        assert mock_upload.call_count == 3
        assert mock_sleep.call_count == 2

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

    def test_episode_stores_file_metadata(self, tmp_path):
        """Episode stores file_path, duration_seconds, file_size_bytes regardless of S3."""
        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)
        src_audio = tmp_path / "my-podcast.mp3"
        src_audio.write_bytes(b"FAKE_MP3")
        storage_dir = tmp_path / "audio"
        generation_result = self._make_generation_result(
            audio_file_path=str(src_audio),
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
            mock_settings.LOCAL_AUDIO_STORAGE_PATH = str(storage_dir)
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "success"
        # No-S3 path persists audio off /tmp; transcript_path is untouched (#292)
        assert episode.file_path == str(storage_dir / f"episode-{episode_id}.mp3")
        assert episode.duration_seconds == 450.5
        assert episode.file_size_bytes == 9_999_999
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

    def test_absorbs_orphaned_s3_object_when_episode_deleted_mid_finalization(self):
        """Issue #366: the episode row fetched at the top of the task
        (unlocked, via db.get) can be deleted by another transaction before the
        final commit. SQLAlchemy raises StaleDataError on that 0-row-matched
        UPDATE. The S3 object already uploaded by this point must be queued
        for deletion instead of silently orphaned (no s3:ListBucket in IAM)."""
        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id, user_id)
        generation_result = self._make_generation_result()

        mock_db = MagicMock()
        # First call: initial fetch (row exists). Second call: post-StaleDataError
        # recheck confirming the row is genuinely gone.
        mock_db.get.side_effect = [episode, None]
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        # First commit ('uploading' status) succeeds; final commit hits the race.
        mock_db.commit.side_effect = [None, StaleDataError("stale", 1, 0)]

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
            patch("src.tasks.podcast_generation._queue_orphaned_storage") as mock_queue,
        ):
            mock_settings.AWS_S3_BUCKET = "test-bucket"
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "absorbed"
        mock_queue.assert_called_once_with(
            s3_key=upload_result["s3_key"], file_path=None, tenant_id=episode.tenant_id
        )

    def test_absorbs_orphaned_local_file_when_episode_deleted_mid_finalization_no_s3(
        self, tmp_path
    ):
        """Same race as above, but with no S3 bucket configured: the durable
        artifact is the locally-persisted copy, so that path is queued."""
        episode_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id)
        src_audio = tmp_path / "episode-abc.mp3"
        src_audio.write_bytes(b"FAKE_MP3")
        storage_dir = tmp_path / "audio"
        generation_result = self._make_generation_result(audio_file_path=str(src_audio))

        mock_db = MagicMock()
        mock_db.get.side_effect = [episode, None]
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        # No-S3 branch only ever commits once (the final commit).
        mock_db.commit.side_effect = StaleDataError("stale", 1, 0)

        with (
            patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
            patch("src.tasks.podcast_generation.settings") as mock_settings,
            patch("src.tasks.podcast_generation._queue_orphaned_storage") as mock_queue,
        ):
            mock_settings.AWS_S3_BUCKET = None
            mock_settings.LOCAL_AUDIO_STORAGE_PATH = str(storage_dir)
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "absorbed"
        expected_path = str(storage_dir / f"episode-{episode_id}.mp3")
        mock_queue.assert_called_once_with(
            s3_key=None, file_path=expected_path, tenant_id=episode.tenant_id
        )

    def test_does_not_absorb_when_row_still_present_after_staledata_error(self):
        """Extremely defensive: if the post-error recheck still finds the row,
        something other than a delete race is going on — do not queue anything
        for deletion, just fail cleanly."""
        episode_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        episode = _make_mock_episode(episode_id, user_id)
        generation_result = self._make_generation_result()

        mock_db = MagicMock()
        mock_db.get.side_effect = [episode, episode]  # still present on recheck
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.commit.side_effect = [None, StaleDataError("stale", 1, 0)]

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
            patch("src.tasks.podcast_generation._queue_orphaned_storage") as mock_queue,
        ):
            mock_settings.AWS_S3_BUCKET = "test-bucket"
            result = self._invoke_finalize(episode_id, generation_result, mock_db)

        assert result["status"] == "failed"
        mock_queue.assert_not_called()


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

    def test_generate_falls_back_to_sync_when_broker_unavailable(self):
        """When .delay() raises (broker down), finalize runs synchronously."""
        episode_id = str(uuid.uuid4())
        mock_audio_path = "/tmp/test_podcast.mp3"

        mock_audio_segment = MagicMock()
        mock_audio_segment.__len__ = MagicMock(return_value=60_000)

        with (
            patch("src.tasks.podcast_generation.finalize_episode_generation_task") as mock_finalize,
            patch("podcastfy.client.generate_podcast", return_value=mock_audio_path),
            patch("src.tasks.podcast_generation.os.path.getsize", return_value=1000),
            patch("src.tasks.podcast_generation.AudioSegment") as mock_audio_cls,
        ):
            # Simulate broker failure on .delay()
            mock_finalize.delay.side_effect = ConnectionError("Redis unavailable")
            mock_finalize.return_value = {"status": "success"}
            mock_audio_cls.from_file.return_value = mock_audio_segment

            from src.tasks.podcast_generation import generate_podcast_task
            result = _invoke_task(
                generate_podcast_task,
                episode_id=episode_id,
                urls=["https://example.com"],
            )

        # Generation still succeeds even though broker was down
        assert result["status"] == "success"
        # .delay() was attempted
        mock_finalize.delay.assert_called_once()
        # Synchronous fallback was called
        mock_finalize.assert_called_once_with(
            episode_id=episode_id,
            generation_result=result,
        )


# ============================================================================
# Non-retryable S3 error tests
# ============================================================================

class TestNonRetryableS3Errors:
    """Tests for non-retryable S3 client errors being raised (not swallowed)."""

    def _invoke_upload(self, **kwargs):
        from src.tasks.s3_upload import upload_to_s3_task
        return _invoke_task(upload_to_s3_task, **kwargs)

    def test_non_retryable_client_error_raises(self):
        """Non-retryable S3 errors (NoSuchBucket, etc.) are raised, not returned as dict."""
        import pytest

        error_response = {"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}}
        client_error = ClientError(error_response, "PutObject")

        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_s3 = MagicMock()
            mock_s3.upload_file.side_effect = client_error
            mock_boto.client.return_value = mock_s3

            with pytest.raises(ClientError):
                self._invoke_upload(
                    file_path="/tmp/audio.mp3",
                    s3_key="test/key.mp3",
                    bucket_name="nonexistent-bucket",
                )

    def test_retryable_client_error_returns_failed_dict_after_max_retries(self):
        """Retryable S3 errors return a failed dict after all retries are exhausted."""
        from src.tasks.s3_upload import upload_to_s3_task

        error_response = {"Error": {"Code": "InternalError", "Message": "Internal error"}}
        client_error = ClientError(error_response, "PutObject")

        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
            patch.object(
                upload_to_s3_task,
                "retry",
                side_effect=upload_to_s3_task.MaxRetriesExceededError(),
            ),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_s3 = MagicMock()
            mock_s3.upload_file.side_effect = client_error
            mock_boto.client.return_value = mock_s3
            upload_to_s3_task.request.update(retries=3)

            result = self._invoke_upload(
                file_path="/tmp/audio.mp3",
                s3_key="test/key.mp3",
                bucket_name="my-bucket",
            )

        assert result["status"] == "failed"
        assert "InternalError" in result["error"]


# ============================================================================
# Temp-file cleanup (issue #275)
# ============================================================================

class TestTempFileCleanup:
    """The composed audio temp file must be deleted once it's safely in S3, but
    only when it lives under the system temp dir and never while a retry could
    still need it."""

    def _invoke_upload(self, **kwargs):
        from src.tasks.s3_upload import upload_to_s3_task
        return _invoke_task(upload_to_s3_task, **kwargs)

    def _make_temp_file(self) -> str:
        """Create a real file under the system temp dir; return its path."""
        fd, path = tempfile.mkstemp(prefix="composed_", suffix=".mp3")
        os.write(fd, b"fake audio bytes")
        os.close(fd)
        return path

    def test_temp_file_deleted_after_successful_upload(self):
        """Success path: a temp-dir file is removed once uploaded to S3."""
        path = self._make_temp_file()
        try:
            with (
                patch("src.tasks.s3_upload.settings") as mock_settings,
                patch("src.tasks.s3_upload.boto3") as mock_boto,
            ):
                mock_settings.AWS_REGION = "us-east-1"
                mock_boto.client.return_value = MagicMock()

                result = self._invoke_upload(
                    file_path=path,
                    s3_key="test/key.mp3",
                    bucket_name="my-bucket",
                )

            assert result["status"] == "success"
            assert not os.path.exists(path), "temp file should be deleted after upload"
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_non_temp_file_is_not_deleted(self, tmp_path):
        """Guard: a file OUTSIDE the system temp dir must never be deleted."""
        # tmp_path is pytest's per-test dir; force it outside tempfile.gettempdir()
        # by pointing gettempdir() elsewhere so this path is treated as non-temp.
        persistent = tmp_path / "audio.mp3"
        persistent.write_bytes(b"keep me")
        fake_temp_root = tmp_path / "systmp"
        fake_temp_root.mkdir()

        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=7),
            patch("src.tasks.s3_upload.tempfile.gettempdir", return_value=str(fake_temp_root)),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_boto.client.return_value = MagicMock()

            result = self._invoke_upload(
                file_path=str(persistent),
                s3_key="test/key.mp3",
                bucket_name="my-bucket",
            )

        assert result["status"] == "success"
        assert persistent.exists(), "non-temp file must be preserved"

    def test_run_dir_removed_after_successful_upload(self):
        """Issue #309: uploading a file that lives in a podcastfy per-run dir must
        remove the whole dir — audio AND the transcript beside it."""
        import shutil
        from src.tasks.s3_upload import GENERATION_RUN_DIR_PREFIX

        run_dir = tempfile.mkdtemp(prefix=GENERATION_RUN_DIR_PREFIX)
        audio = os.path.join(run_dir, "podcast_abc.mp3")
        transcript = os.path.join(run_dir, "transcript_abc.txt")
        try:
            with open(audio, "wb") as f:
                f.write(b"fake audio bytes")
            with open(transcript, "w") as f:
                f.write("fake transcript")

            with (
                patch("src.tasks.s3_upload.settings") as mock_settings,
                patch("src.tasks.s3_upload.boto3") as mock_boto,
            ):
                mock_settings.AWS_REGION = "us-east-1"
                mock_boto.client.return_value = MagicMock()

                result = self._invoke_upload(
                    file_path=audio,
                    s3_key="test/key.mp3",
                    bucket_name="my-bucket",
                )

            assert result["status"] == "success"
            assert not os.path.exists(run_dir), (
                "the per-run dir (audio + transcript) should be removed after upload"
            )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_run_dir_outside_temp_root_is_preserved(self, tmp_path):
        """Guard: a podcastfy-run-* directory OUTSIDE the system temp root must
        never be deleted (nor its files)."""
        fake_temp_root = tmp_path / "systmp"
        fake_temp_root.mkdir()
        run_dir = tmp_path / "podcastfy-run-persistent"
        run_dir.mkdir()
        audio = run_dir / "podcast.mp3"
        audio.write_bytes(b"keep me")
        transcript = run_dir / "transcript.txt"
        transcript.write_text("keep me")

        with (
            patch("src.tasks.s3_upload.settings") as mock_settings,
            patch("src.tasks.s3_upload.boto3") as mock_boto,
            patch("src.tasks.s3_upload.os.path.getsize", return_value=7),
            patch("src.tasks.s3_upload.tempfile.gettempdir", return_value=str(fake_temp_root)),
        ):
            mock_settings.AWS_REGION = "us-east-1"
            mock_boto.client.return_value = MagicMock()

            result = self._invoke_upload(
                file_path=str(audio),
                s3_key="test/key.mp3",
                bucket_name="my-bucket",
            )

        assert result["status"] == "success"
        assert audio.exists() and transcript.exists(), "non-temp run dir must be preserved"

    def test_temp_file_kept_while_retrying(self):
        """Retry path: a transient error that triggers a retry must NOT delete
        the file — the next retry still needs it."""
        path = self._make_temp_file()
        try:
            from src.tasks.s3_upload import upload_to_s3_task

            # retry() raises Retry; the task never reaches a terminal branch.
            with (
                patch("src.tasks.s3_upload.settings") as mock_settings,
                patch("src.tasks.s3_upload.boto3") as mock_boto,
                patch("src.tasks.s3_upload.os.path.getsize", return_value=16),
                patch.object(
                    upload_to_s3_task,
                    "retry",
                    side_effect=RuntimeError("retry-signal"),
                ),
            ):
                mock_settings.AWS_REGION = "us-east-1"
                mock_s3 = MagicMock()
                mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
                mock_boto.client.return_value = mock_s3
                upload_to_s3_task.request.update(retries=0)

                try:
                    self._invoke_upload(
                        file_path=path,
                        s3_key="test/key.mp3",
                        bucket_name="my-bucket",
                    )
                except RuntimeError:
                    pass  # the retry signal — expected

            assert os.path.exists(path), "file must be kept while a retry is pending"
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_temp_file_deleted_after_retries_exhausted(self):
        """Terminal-failure path: once retries are exhausted no retry will read
        the file, so the temp artifact must be cleaned up to avoid leaking /tmp."""
        path = self._make_temp_file()
        try:
            from src.tasks.s3_upload import upload_to_s3_task

            with (
                patch("src.tasks.s3_upload.settings") as mock_settings,
                patch("src.tasks.s3_upload.boto3") as mock_boto,
                patch("src.tasks.s3_upload.os.path.getsize", return_value=16),
                patch.object(
                    upload_to_s3_task,
                    "retry",
                    side_effect=upload_to_s3_task.MaxRetriesExceededError(),
                ),
            ):
                mock_settings.AWS_REGION = "us-east-1"
                mock_s3 = MagicMock()
                mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
                mock_boto.client.return_value = mock_s3
                upload_to_s3_task.request.update(retries=3)

                result = self._invoke_upload(
                    file_path=path,
                    s3_key="test/key.mp3",
                    bucket_name="my-bucket",
                )

            assert result["status"] == "failed"
            assert not os.path.exists(path), "temp file should be deleted after terminal failure"
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_temp_file_deleted_on_non_retryable_error(self):
        """Non-retryable failure (e.g. AccessDenied) is terminal — it raises and
        no retry follows, so the temp artifact must still be cleaned up."""
        path = self._make_temp_file()
        try:
            client_error = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}},
                "PutObject",
            )
            with (
                patch("src.tasks.s3_upload.settings") as mock_settings,
                patch("src.tasks.s3_upload.boto3") as mock_boto,
                patch("src.tasks.s3_upload.os.path.getsize", return_value=16),
            ):
                mock_settings.AWS_REGION = "us-east-1"
                mock_s3 = MagicMock()
                mock_s3.upload_file.side_effect = client_error
                mock_boto.client.return_value = mock_s3

                try:
                    self._invoke_upload(
                        file_path=path,
                        s3_key="test/key.mp3",
                        bucket_name="my-bucket",
                    )
                except ClientError:
                    pass  # non-retryable errors re-raise — expected

            assert not os.path.exists(path), "temp file should be deleted on terminal non-retryable error"
        finally:
            if os.path.exists(path):
                os.remove(path)
