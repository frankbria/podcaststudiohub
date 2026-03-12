"""
Tests for Celery task retry configuration and exponential backoff behavior.

Verifies that all tasks:
- Have max_retries configured
- Retry on transient errors with exponential backoff
- Return failure dicts after max retries are exhausted
- Do NOT retry on permanent/validation errors
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Helpers (shared with test_s3_upload.py pattern)
# ============================================================================

def _invoke_task_at_retry(task, retry_count: int, **kwargs):
	"""
	Invoke a Celery task simulating a specific retry attempt.

	Sets self.request.retries = retry_count so that:
	- If retry_count < max_retries: self.retry() raises Retry
	- If retry_count >= max_retries: self.retry() raises MaxRetriesExceededError

	Args:
		task: The Celery task object (bind=True)
		retry_count: Simulated current retry count (0 = first attempt)
		**kwargs: Task arguments

	Returns:
		Task return value (only when retries are exhausted or success)

	Raises:
		Retry: When task triggers a retry (retry_count < max_retries)
	"""
	task.request.update(
		id="test-task-id-" + str(uuid.uuid4()),
		retries=retry_count,
	)
	with patch.object(task, 'update_state', MagicMock()):
		return task.run(**kwargs)


def _invoke_task_exhausted(task, **kwargs):
	"""
	Invoke a task simulating all retries have been exhausted.

	Sets retries = max_retries so self.retry() raises MaxRetriesExceededError,
	causing the task to return its failure dict instead of retrying.
	"""
	return _invoke_task_at_retry(task, retry_count=task.max_retries, **kwargs)


# ============================================================================
# Task max_retries configuration tests
# ============================================================================

class TestTaskRetryConfiguration:
	"""Verify each task has the correct max_retries set."""

	def test_s3_upload_max_retries(self):
		"""upload_to_s3_task has max_retries=3."""
		from src.tasks.s3_upload import upload_to_s3_task
		assert upload_to_s3_task.max_retries == 3

	def test_audio_composition_max_retries(self):
		"""merge_audio_snippets_task has max_retries=2."""
		from src.tasks.audio_composition import merge_audio_snippets_task
		assert merge_audio_snippets_task.max_retries == 2

	def test_platform_distribution_max_retries(self):
		"""distribute_to_platform_task has max_retries=5."""
		from src.tasks.platform_distribution import distribute_to_platform_task
		assert distribute_to_platform_task.max_retries == 5

	def test_podcast_generation_max_retries(self):
		"""generate_podcast_task has max_retries=3."""
		from src.tasks.podcast_generation import generate_podcast_task
		assert generate_podcast_task.max_retries == 3


# ============================================================================
# S3 upload retry tests
# ============================================================================

class TestS3UploadRetry:
	"""Tests for retry behavior in upload_to_s3_task."""

	def test_raises_exception_on_first_transient_error(self):
		"""On first transient error, task raises the exception (triggering retry)."""
		from src.tasks.s3_upload import upload_to_s3_task

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
			mock_boto.client.return_value = mock_s3

			# Celery re-raises the original exception (not Retry) via raise_with_context
			with pytest.raises(RuntimeError, match="Connection timeout"):
				_invoke_task_at_retry(
					upload_to_s3_task,
					retry_count=0,
					file_path="/tmp/audio.mp3",
					s3_key="test/key.mp3",
					bucket_name="my-bucket",
				)

	def test_returns_failed_dict_when_retries_exhausted(self):
		"""After max_retries, upload_to_s3_task returns failure dict."""
		from src.tasks.s3_upload import upload_to_s3_task

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = RuntimeError("Connection timeout")
			mock_boto.client.return_value = mock_s3

			result = _invoke_task_exhausted(
				upload_to_s3_task,
				file_path="/tmp/audio.mp3",
				s3_key="test/key.mp3",
				bucket_name="my-bucket",
			)

		assert result["status"] == "failed"
		assert result["s3_url"] is None
		assert "Connection timeout" in result["error"]

	def test_uses_exponential_backoff_countdown(self):
		"""Retry countdown follows exponential backoff: 5 * 2^retries."""
		from src.tasks.s3_upload import upload_to_s3_task

		captured_countdown = {}

		original_retry = upload_to_s3_task.retry

		def capture_retry(*args, countdown=None, **kwargs):
			captured_countdown["value"] = countdown
			return original_retry(*args, countdown=countdown, **kwargs)

		with (
			patch("src.tasks.s3_upload.settings") as mock_settings,
			patch("src.tasks.s3_upload.boto3") as mock_boto,
			patch("src.tasks.s3_upload.os.path.getsize", return_value=512),
			patch.object(upload_to_s3_task, 'retry', side_effect=capture_retry),
		):
			mock_settings.AWS_REGION = "us-east-1"
			mock_s3 = MagicMock()
			mock_s3.upload_file.side_effect = RuntimeError("Transient error")
			mock_boto.client.return_value = mock_s3

			with pytest.raises(Exception):
				_invoke_task_at_retry(
					upload_to_s3_task,
					retry_count=1,  # Second attempt
					file_path="/tmp/audio.mp3",
					s3_key="test/key.mp3",
					bucket_name="my-bucket",
				)

		# retry_count=1 → countdown = 5 * 2^1 = 10 seconds
		assert captured_countdown.get("value") == 10

	def test_non_retryable_client_error_still_raises(self):
		"""Non-retryable S3 errors (NoSuchBucket, etc.) are re-raised, not retried."""
		from src.tasks.s3_upload import upload_to_s3_task
		from botocore.exceptions import ClientError

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

			# Non-retryable errors should raise ClientError (not Retry, not dict)
			with pytest.raises(ClientError):
				_invoke_task_at_retry(
					upload_to_s3_task,
					retry_count=0,
					file_path="/tmp/audio.mp3",
					s3_key="test/key.mp3",
					bucket_name="my-bucket",
				)


# ============================================================================
# Audio composition retry tests
# ============================================================================

class TestAudioCompositionRetry:
	"""Tests for retry behavior in merge_audio_snippets_task."""

	def test_raises_exception_on_first_error(self):
		"""On first error, merge_audio_snippets_task raises exception (triggering retry)."""
		import sys
		from src.tasks.audio_composition import merge_audio_snippets_task

		# AudioSegment is imported locally inside the task function via
		# 'from pydub import AudioSegment'. Patch via pydub module directly.
		mock_audio_segment = MagicMock()
		mock_audio_segment.empty.side_effect = RuntimeError("FFmpeg not found")

		with patch.dict(sys.modules, {'pydub': MagicMock(AudioSegment=mock_audio_segment)}):
			# Celery re-raises the original exception via raise_with_context
			with pytest.raises(RuntimeError, match="FFmpeg not found"):
				_invoke_task_at_retry(
					merge_audio_snippets_task,
					retry_count=0,
					episode_id=str(uuid.uuid4()),
					timeline=[],
					output_path="/tmp/output.mp3",
				)

	def test_returns_failed_dict_when_retries_exhausted(self):
		"""After max_retries, merge_audio_snippets_task returns failure dict."""
		import sys
		from src.tasks.audio_composition import merge_audio_snippets_task

		episode_id = str(uuid.uuid4())

		mock_audio_segment = MagicMock()
		mock_audio_segment.empty.side_effect = RuntimeError("FFmpeg not found")

		with patch.dict(sys.modules, {'pydub': MagicMock(AudioSegment=mock_audio_segment)}):
			result = _invoke_task_exhausted(
				merge_audio_snippets_task,
				episode_id=episode_id,
				timeline=[],
				output_path="/tmp/output.mp3",
			)

		assert result["status"] == "failed"
		assert result["output_path"] is None
		assert "FFmpeg not found" in result["error"]


# ============================================================================
# Platform distribution retry tests
# ============================================================================

class TestPlatformDistributionRetry:
	"""Tests for retry behavior in distribute_to_platform_task."""

	def test_raises_exception_on_transient_error(self):
		"""On transient error, distribute_to_platform_task raises exception (triggering retry)."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		# 'requests' is imported locally inside _distribute_via_webhook, so patch
		# at the requests module level using patch().
		with patch("requests.post") as mock_post:
			mock_post.side_effect = ConnectionError("refused")

			# Celery re-raises the original exception via raise_with_context
			with pytest.raises(Exception):
				_invoke_task_at_retry(
					distribute_to_platform_task,
					retry_count=0,
					episode_id=str(uuid.uuid4()),
					platform="webhook",
					platform_config={"webhook_url": "https://example.com/hook"},
					episode_metadata={"title": "Test Episode"},
				)

	def test_returns_failed_dict_when_retries_exhausted(self):
		"""After max_retries, distribute_to_platform_task returns failure dict."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode_id = str(uuid.uuid4())

		with patch("requests.post") as mock_post:
			mock_post.side_effect = ConnectionError("Network unavailable")

			result = _invoke_task_exhausted(
				distribute_to_platform_task,
				episode_id=episode_id,
				platform="webhook",
				platform_config={"webhook_url": "https://example.com/hook"},
				episode_metadata={"title": "Test Episode"},
			)

		assert result["status"] == "failed"
		assert result["platform"] == "webhook"
		assert "Network unavailable" in result["error"]

	def test_unsupported_platform_not_retried(self):
		"""ValueError for unsupported platform returns failure dict immediately (no retry)."""
		from src.tasks.platform_distribution import distribute_to_platform_task

		episode_id = str(uuid.uuid4())

		# Even on first attempt, ValueError should return failure dict (not retry)
		result = _invoke_task_at_retry(
			distribute_to_platform_task,
			retry_count=0,
			episode_id=episode_id,
			platform="unsupported_platform",
			platform_config={},
			episode_metadata={},
		)

		assert result["status"] == "failed"
		assert "unsupported_platform" in result["error"].lower() or "Unsupported" in result["error"]


# ============================================================================
# Podcast generation retry tests
# ============================================================================

class TestPodcastGenerationRetry:
	"""Tests for retry behavior in generate_podcast_task."""

	@staticmethod
	def _mock_podcastfy_modules(generate_podcast_side_effect=None):
		"""
		Create a sys.modules patch for podcastfy.

		generate_podcast_task imports podcastfy lazily inside the function body.
		We mock sys.modules so the import succeeds and the mock is used.
		"""
		import sys
		mock_generate_podcast = MagicMock()
		if generate_podcast_side_effect is not None:
			mock_generate_podcast.side_effect = generate_podcast_side_effect
		mock_client = MagicMock()
		mock_client.generate_podcast = mock_generate_podcast
		mock_podcastfy = MagicMock()
		mock_podcastfy.client = mock_client
		return patch.dict(sys.modules, {
			'podcastfy': mock_podcastfy,
			'podcastfy.client': mock_client,
		})

	def test_raises_exception_on_first_error(self):
		"""On first error, generate_podcast_task raises exception (triggering retry)."""
		from src.tasks.podcast_generation import generate_podcast_task

		with self._mock_podcastfy_modules(RuntimeError("LLM API unavailable")):
			with patch("src.tasks.podcast_generation.finalize_episode_generation_task"):
				# Celery re-raises the original exception via raise_with_context
				with pytest.raises(RuntimeError, match="LLM API unavailable"):
					_invoke_task_at_retry(
						generate_podcast_task,
						retry_count=0,
						episode_id=str(uuid.uuid4()),
						urls=["https://example.com"],
					)

	def test_returns_failed_dict_when_retries_exhausted(self):
		"""After max_retries, generate_podcast_task returns failure dict."""
		from src.tasks.podcast_generation import generate_podcast_task

		episode_id = str(uuid.uuid4())

		with self._mock_podcastfy_modules(RuntimeError("LLM API unavailable")):
			result = _invoke_task_exhausted(
				generate_podcast_task,
				episode_id=episode_id,
				urls=["https://example.com"],
			)

		assert result["status"] == "failed"
		assert result["audio_file_path"] is None
		assert "LLM API unavailable" in result["error"]

	def test_backoff_countdown_on_second_retry(self):
		"""Countdown on second retry (retry_count=1) is 10 seconds."""
		from src.tasks.podcast_generation import generate_podcast_task

		captured_countdown = {}
		original_retry = generate_podcast_task.retry

		def capture_retry(*args, countdown=None, **kwargs):
			captured_countdown["value"] = countdown
			return original_retry(*args, countdown=countdown, **kwargs)

		with (
			self._mock_podcastfy_modules(RuntimeError("Transient error")),
			patch.object(generate_podcast_task, 'retry', side_effect=capture_retry),
		):
			with pytest.raises(Exception):
				_invoke_task_at_retry(
					generate_podcast_task,
					retry_count=1,
					episode_id=str(uuid.uuid4()),
					urls=["https://example.com"],
				)

		# retry_count=1 → countdown = 5 * 2^1 = 10 seconds
		assert captured_countdown.get("value") == 10
