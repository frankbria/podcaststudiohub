"""
Tests for retry configuration on all Celery tasks.

Verifies that:
- Each task has the required max_retries setting
- Transient errors trigger self.retry() with exponential backoff
- After retries are exhausted, a failed result dict is returned
- Non-retryable errors are handled appropriately per task
"""

import sys
import types
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError


def _mock_podcastfy_modules():
	"""Return mocked podcastfy client + modules dict for sys.modules patching."""
	mock_podcastfy = types.ModuleType("podcastfy")
	mock_client_module = types.ModuleType("podcastfy.client")
	mock_gen = MagicMock(return_value="/tmp/output.mp3")
	mock_client_module.generate_podcast = mock_gen
	mock_podcastfy.client = mock_client_module
	return mock_gen, {
		"podcastfy": mock_podcastfy,
		"podcastfy.client": mock_client_module,
	}


# ============================================================================
# Helpers
# ============================================================================


def _make_celery_retry_exception(task):
	"""Return a MaxRetriesExceededError for the given task."""
	return task.MaxRetriesExceededError()


def _make_client_error(code: str, message: str = "AWS error") -> ClientError:
	return ClientError({"Error": {"Code": code, "Message": message}}, "Operation")


def _uploaded_episode_session():
	"""A mock sync session whose Episode has a committed s3_url.

	distribute_to_platform_task loads the Episode and refuses to publish without an
	uploaded audio URL (issue #211), so distribution retry tests must present an
	episode that has already been uploaded to reach the platform-dispatch path.
	"""
	episode = MagicMock()
	episode.episode_metadata = {"title": "Ep", "description": "d"}
	episode.duration_seconds = 60.0
	episode.s3_url = "https://bucket.s3.amazonaws.com/podcasts/episode-x.mp3"
	session = MagicMock()
	session.get.return_value = episode
	session.__enter__ = MagicMock(return_value=session)
	session.__exit__ = MagicMock(return_value=False)
	return session


# ============================================================================
# upload_to_s3_task retry tests
# ============================================================================


class TestUploadToS3TaskRetry:

	def test_task_has_max_retries_3(self):
		"""upload_to_s3_task must declare max_retries=3."""
		from src.tasks.s3_upload import upload_to_s3_task
		assert upload_to_s3_task.max_retries == 3

	def test_retryable_client_error_calls_retry(self):
		"""Retryable S3 ClientError must trigger self.retry() with backoff."""
		from src.tasks.s3_upload import upload_to_s3_task

		client_error = _make_client_error("InternalError", "Internal server error")

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
			patch.object(
				upload_to_s3_task,
				"retry",
				side_effect=_make_celery_retry_exception(upload_to_s3_task),
			) as mock_retry,
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = client_error
			mock_boto.client.return_value = mock_s3
			upload_to_s3_task.request.update(retries=0)

			result = upload_to_s3_task.run(
				file_path="/tmp/audio.mp3",
				s3_key="test/key.mp3",
				bucket_name="my-bucket",
			)

		mock_retry.assert_called_once()
		assert result["status"] == "failed"

	def test_generic_exception_calls_retry(self):
		"""Generic exceptions must trigger self.retry() with backoff."""
		from src.tasks.s3_upload import upload_to_s3_task

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
			patch.object(
				upload_to_s3_task,
				"retry",
				side_effect=_make_celery_retry_exception(upload_to_s3_task),
			) as mock_retry,
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
			mock_boto.client.return_value = mock_s3
			upload_to_s3_task.request.update(retries=0)

			result = upload_to_s3_task.run(
				file_path="/tmp/audio.mp3",
				s3_key="test/key.mp3",
				bucket_name="my-bucket",
			)

		mock_retry.assert_called_once()
		assert result["status"] == "failed"

	def test_retry_called_with_countdown(self):
		"""self.retry() must be called with a countdown (exponential backoff)."""
		from src.tasks.s3_upload import upload_to_s3_task

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
			patch.object(
				upload_to_s3_task,
				"retry",
				side_effect=_make_celery_retry_exception(upload_to_s3_task),
			) as mock_retry,
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = RuntimeError("Timeout")
			mock_boto.client.return_value = mock_s3
			upload_to_s3_task.request.update(retries=0)

			upload_to_s3_task.run(
				file_path="/tmp/audio.mp3",
				s3_key="test/key.mp3",
				bucket_name="my-bucket",
			)

		call_kwargs = mock_retry.call_args.kwargs
		assert "countdown" in call_kwargs
		assert call_kwargs["countdown"] == 5  # First retry: 5 seconds

	def test_retry_countdown_increases_with_retry_count(self):
		"""Backoff countdown increases with each retry attempt."""
		from src.tasks.s3_upload import upload_to_s3_task

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
			patch.object(
				upload_to_s3_task,
				"retry",
				side_effect=_make_celery_retry_exception(upload_to_s3_task),
			) as mock_retry,
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = RuntimeError("Timeout")
			mock_boto.client.return_value = mock_s3
			# Simulate second retry (retries already attempted=1)
			upload_to_s3_task.request.update(retries=1)

			upload_to_s3_task.run(
				file_path="/tmp/audio.mp3",
				s3_key="test/key.mp3",
				bucket_name="my-bucket",
			)

		call_kwargs = mock_retry.call_args.kwargs
		assert call_kwargs["countdown"] == 10  # Second retry: 10 seconds

	def test_non_retryable_client_error_raises(self):
		"""Non-retryable S3 errors must be raised without calling retry."""
		import pytest
		from src.tasks.s3_upload import upload_to_s3_task

		client_error = _make_client_error("NoSuchBucket", "Bucket not found")

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
			patch.object(upload_to_s3_task, "update_state"),
			patch.object(upload_to_s3_task, "retry") as mock_retry,
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = client_error
			mock_boto.client.return_value = mock_s3
			upload_to_s3_task.request.update(id="test-task-id")

			with pytest.raises(ClientError):
				upload_to_s3_task.run(
					file_path="/tmp/audio.mp3",
					s3_key="test/key.mp3",
					bucket_name="nonexistent-bucket",
				)

		mock_retry.assert_not_called()


# ============================================================================
# merge_audio_snippets_task retry tests
# ============================================================================


def _mock_pydub_modules():
	"""Return mocked AudioSegment class + modules dict for sys.modules patching."""
	mock_audio_segment_class = MagicMock()
	mock_pydub = types.ModuleType("pydub")
	mock_pydub.AudioSegment = mock_audio_segment_class
	return mock_audio_segment_class, {
		"pydub": mock_pydub,
		"pydub.AudioSegment": mock_audio_segment_class,
	}


class TestMergeAudioSnippetsTaskRetry:

	def test_task_has_max_retries_2(self):
		"""merge_audio_snippets_task must declare max_retries=2."""
		from src.tasks.audio_composition import merge_audio_snippets_task
		assert merge_audio_snippets_task.max_retries == 2

	def test_exception_triggers_retry(self):
		"""Any exception during composition must trigger self.retry()."""
		from src.tasks.audio_composition import merge_audio_snippets_task

		mock_cls, mock_modules = _mock_pydub_modules()
		mock_cls.empty.return_value = MagicMock()
		mock_cls.from_file.side_effect = RuntimeError("FFmpeg crashed")

		timeline = [{"file_path": "/tmp/seg.mp3"}]

		with (
			patch.dict(sys.modules, mock_modules),
			patch.object(merge_audio_snippets_task, "update_state"),
			patch.object(
				merge_audio_snippets_task,
				"retry",
				side_effect=_make_celery_retry_exception(merge_audio_snippets_task),
			) as mock_retry,
		):
			merge_audio_snippets_task.request.update(retries=0)
			result = merge_audio_snippets_task.run(
				episode_id="ep-retry-01",
				timeline=timeline,
				output_path="/tmp/out.mp3",
			)

		mock_retry.assert_called_once()
		assert result["status"] == "failed"

	def test_retry_countdown_on_first_attempt(self):
		"""First retry countdown must be 5 seconds."""
		from src.tasks.audio_composition import merge_audio_snippets_task

		mock_cls, mock_modules = _mock_pydub_modules()
		mock_cls.empty.return_value = MagicMock()
		mock_cls.from_file.side_effect = RuntimeError("Disk full")

		with (
			patch.dict(sys.modules, mock_modules),
			patch.object(merge_audio_snippets_task, "update_state"),
			patch.object(
				merge_audio_snippets_task,
				"retry",
				side_effect=_make_celery_retry_exception(merge_audio_snippets_task),
			) as mock_retry,
		):
			merge_audio_snippets_task.request.update(retries=0)
			merge_audio_snippets_task.run(
				episode_id="ep-backoff-01",
				timeline=[{"file_path": "/tmp/seg.mp3"}],
				output_path="/tmp/out.mp3",
			)

		assert mock_retry.call_args.kwargs["countdown"] == 5


# ============================================================================
# distribute_to_platform_task retry tests
# ============================================================================


class TestDistributeToPlatformTaskRetry:

	def test_task_has_max_retries_5(self):
		"""distribute_to_platform_task must declare max_retries=5."""
		from src.tasks.platform_distribution import distribute_to_platform_task
		assert distribute_to_platform_task.max_retries == 5

	def test_transient_exception_triggers_retry(self):
		"""Transient exceptions during distribution must trigger self.retry()."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		with (
			patch("src.tasks.platform_distribution.SyncSessionLocal", return_value=_uploaded_episode_session()),
			patch("src.tasks.platform_distribution._decrypt_platform_config") as mock_decrypt,
			patch("src.tasks.platform_distribution._distribute_to_spotify") as mock_spotify,
			patch.object(distribute_to_platform_task, "update_state"),
			patch.object(
				distribute_to_platform_task,
				"retry",
				side_effect=_make_celery_retry_exception(distribute_to_platform_task),
			) as mock_retry,
		):
			mock_decrypt.return_value = {}
			mock_spotify.side_effect = ConnectionError("Network error")
			distribute_to_platform_task.request.update(retries=0)

			result = distribute_to_platform_task.run(
				episode_id="11111111-1111-1111-1111-111111111101",
				platform="spotify",
				platform_config={},
				episode_metadata={},
			)

		mock_retry.assert_called_once()
		assert result["status"] == "failed"

	def test_value_error_does_not_retry(self):
		"""ValueError (unsupported platform) must not trigger retry."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		with (
			patch("src.tasks.platform_distribution.SyncSessionLocal", return_value=_uploaded_episode_session()),
			patch("src.tasks.platform_distribution._decrypt_platform_config") as mock_decrypt,
			patch.object(distribute_to_platform_task, "update_state"),
			patch.object(distribute_to_platform_task, "retry") as mock_retry,
		):
			mock_decrypt.return_value = {}
			distribute_to_platform_task.request.update(retries=0)

			result = distribute_to_platform_task.run(
				episode_id="11111111-1111-1111-1111-111111111102",
				platform="unsupported_platform",
				platform_config={},
				episode_metadata={},
			)

		mock_retry.assert_not_called()
		assert result["status"] == "failed"

	def test_retry_countdown_on_first_attempt(self):
		"""First retry countdown must be 5 seconds."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		with (
			patch("src.tasks.platform_distribution.SyncSessionLocal", return_value=_uploaded_episode_session()),
			patch("src.tasks.platform_distribution._decrypt_platform_config") as mock_decrypt,
			patch("src.tasks.platform_distribution._distribute_to_spotify") as mock_spotify,
			patch.object(distribute_to_platform_task, "update_state"),
			patch.object(
				distribute_to_platform_task,
				"retry",
				side_effect=_make_celery_retry_exception(distribute_to_platform_task),
			) as mock_retry,
		):
			mock_decrypt.return_value = {}
			mock_spotify.side_effect = ConnectionError("Network error")
			distribute_to_platform_task.request.update(retries=0)

			distribute_to_platform_task.run(
				episode_id="11111111-1111-1111-1111-111111111103",
				platform="spotify",
				platform_config={},
				episode_metadata={},
			)

		assert mock_retry.call_args.kwargs["countdown"] == 5


# ============================================================================
# generate_podcast_task retry tests
# ============================================================================


class TestGeneratePodcastTaskRetry:

	def test_task_has_max_retries_3(self):
		"""generate_podcast_task must declare max_retries=3."""
		from src.tasks.podcast_generation import generate_podcast_task
		assert generate_podcast_task.max_retries == 3

	def test_exception_triggers_retry(self):
		"""Exceptions during generation must trigger self.retry()."""
		from src.tasks.podcast_generation import generate_podcast_task

		mock_gen, mock_modules = _mock_podcastfy_modules()
		mock_gen.side_effect = RuntimeError("LLM API unavailable")

		with (
			patch.dict(sys.modules, mock_modules),
			patch.object(generate_podcast_task, "update_state"),
			patch.object(
				generate_podcast_task,
				"retry",
				side_effect=_make_celery_retry_exception(generate_podcast_task),
			) as mock_retry,
		):
			generate_podcast_task.request.update(retries=0)

			result = generate_podcast_task.run(
				episode_id="ep-gen-01",
				urls=["https://example.com"],
			)

		mock_retry.assert_called_once()
		assert result["status"] == "failed"

	def test_retry_countdown_on_first_attempt(self):
		"""First retry countdown must be 5 seconds."""
		from src.tasks.podcast_generation import generate_podcast_task

		mock_gen, mock_modules = _mock_podcastfy_modules()
		mock_gen.side_effect = RuntimeError("LLM API unavailable")

		with (
			patch.dict(sys.modules, mock_modules),
			patch.object(generate_podcast_task, "update_state"),
			patch.object(
				generate_podcast_task,
				"retry",
				side_effect=_make_celery_retry_exception(generate_podcast_task),
			) as mock_retry,
		):
			generate_podcast_task.request.update(retries=0)

			generate_podcast_task.run(
				episode_id="ep-gen-02",
				urls=["https://example.com"],
			)

		assert mock_retry.call_args.kwargs["countdown"] == 5

	def test_failed_result_has_correct_shape(self):
		"""After max retries, generate_podcast_task returns expected failure dict."""
		from src.tasks.podcast_generation import generate_podcast_task

		mock_gen, mock_modules = _mock_podcastfy_modules()
		mock_gen.side_effect = RuntimeError("Persistent failure")

		with (
			patch.dict(sys.modules, mock_modules),
			patch.object(generate_podcast_task, "update_state"),
			patch.object(
				generate_podcast_task,
				"retry",
				side_effect=_make_celery_retry_exception(generate_podcast_task),
			),
		):
			generate_podcast_task.request.update(retries=0)

			result = generate_podcast_task.run(
				episode_id="ep-gen-03",
				urls=["https://example.com"],
			)

		assert result["status"] == "failed"
		assert result["audio_file_path"] is None
		assert result["transcript_path"] is None
		assert result["duration_seconds"] == 0
		assert result["file_size_bytes"] == 0
		assert "Persistent failure" in result["error"]


# ============================================================================
# finalize_episode_generation_task retry tests
# ============================================================================


class TestFinalizeEpisodeGenerationTaskRetry:

	def test_task_has_max_retries_3(self):
		"""finalize_episode_generation_task must declare max_retries=3."""
		from src.tasks.podcast_generation import finalize_episode_generation_task
		assert finalize_episode_generation_task.max_retries == 3

	def test_db_error_triggers_retry(self):
		"""Database errors during finalization must trigger self.retry()."""
		import uuid
		from src.tasks.podcast_generation import finalize_episode_generation_task

		episode_id = str(uuid.uuid4())
		generation_result = {
			"status": "success",
			"audio_file_path": "/tmp/ep.mp3",
			"transcript_path": "/tmp/ep_transcript.txt",
			"duration_seconds": 120.0,
			"file_size_bytes": 2_000_000,
			"error": None,
		}

		mock_db = MagicMock()
		mock_db.get.side_effect = RuntimeError("Database connection lost")
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)

		with (
			patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=mock_db),
			patch("src.tasks.podcast_generation.settings") as mock_settings,
			patch.object(finalize_episode_generation_task, "update_state"),
			patch.object(
				finalize_episode_generation_task,
				"retry",
				side_effect=_make_celery_retry_exception(finalize_episode_generation_task),
			) as mock_retry,
		):
			mock_settings.AWS_S3_BUCKET = None
			finalize_episode_generation_task.request.update(retries=0)

			result = finalize_episode_generation_task.run(
				episode_id=episode_id,
				generation_result=generation_result,
			)

		mock_retry.assert_called_once()
		assert result["status"] == "failed"
