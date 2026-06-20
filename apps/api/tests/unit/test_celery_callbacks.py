"""
Unit tests for Celery callback tasks (GAP-028).

Tests cover success callbacks (on_upload_complete, on_composition_complete,
on_distribution_complete, on_workflow_complete) and the error callback
(on_workflow_failure), as well as the build_generation_workflow() builder.

All database interactions are mocked so no real database is required.
"""
import uuid
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_episode(episode_id: str) -> MagicMock:
	"""Return a MagicMock that behaves like an Episode ORM object."""
	ep = MagicMock()
	ep.id = uuid.UUID(episode_id)
	ep.generation_status = "generating"
	ep.generation_progress = {}
	ep.s3_url = None
	ep.s3_key = None
	ep.file_path = None
	ep.duration_seconds = None
	return ep


def _make_sync_session(episode: MagicMock):
	"""
	Return a mock that behaves like a SyncSessionLocal() context manager,
	yielding a session whose .get() returns *episode*.
	"""
	mock_session = MagicMock()
	mock_session.get.return_value = episode
	mock_ctx = MagicMock()
	mock_ctx.__enter__ = MagicMock(return_value=mock_session)
	mock_ctx.__exit__ = MagicMock(return_value=False)
	return mock_ctx, mock_session


def _invoke_task(task, **kwargs):
	"""
	Invoke a bind=True Celery task's underlying run() method without a broker.
	"""
	task.request.update(id="test-" + str(uuid.uuid4()))
	with patch.object(task, "update_state", MagicMock()):
		return task.run(**kwargs)


# ---------------------------------------------------------------------------
# on_upload_complete
# ---------------------------------------------------------------------------

class TestOnUploadComplete:
	"""Tests for the upload success callback."""

	def test_updates_episode_s3_url_on_success(self):
		"""Episode.s3_url and s3_key are saved when upload succeeds."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {
			"status": "success",
			"s3_url": "https://bucket.s3.amazonaws.com/key.mp3",
			"s3_key": "podcasts/key.mp3",
		}

		from src.tasks.callbacks import on_upload_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_upload_complete, result=result, episode_id=episode_id)

		assert episode.s3_url == result["s3_url"]
		assert episode.s3_key == result["s3_key"]
		assert episode.generation_status == "uploading"
		mock_session.commit.assert_called_once()

	def test_skips_update_when_upload_failed(self):
		"""No database update happens when the result indicates failure."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {"status": "failed", "error": "S3 error"}

		from src.tasks.callbacks import on_upload_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_upload_complete, result=result, episode_id=episode_id)

		# Session should not have been entered at all
		mock_ctx.__enter__.assert_not_called()

	def test_handles_missing_episode_gracefully(self):
		"""Callback logs error but does not raise if episode is not found."""
		episode_id = str(uuid.uuid4())
		mock_ctx, mock_session = _make_sync_session(None)  # .get() returns None

		result = {
			"status": "success",
			"s3_url": "https://bucket.s3.amazonaws.com/key.mp3",
			"s3_key": "key.mp3",
		}

		from src.tasks.callbacks import on_upload_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			# Should not raise
			_invoke_task(on_upload_complete, result=result, episode_id=episode_id)

		mock_session.commit.assert_not_called()

	def test_updates_generation_progress(self):
		"""generation_progress is updated with 'upload: complete' on success."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {
			"status": "success",
			"s3_url": "https://bucket.s3.amazonaws.com/k.mp3",
			"s3_key": "k.mp3",
		}

		from src.tasks.callbacks import on_upload_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_upload_complete, result=result, episode_id=episode_id)

		progress = episode.generation_progress
		assert progress.get("upload") == "complete"
		assert "uploaded_at" in progress


# ---------------------------------------------------------------------------
# on_composition_complete
# ---------------------------------------------------------------------------

class TestOnCompositionComplete:
	"""Tests for the audio composition success callback."""

	def test_updates_file_path_and_status(self):
		"""Episode.file_path is saved and status set to 'composing' on success."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {
			"status": "success",
			"output_path": "/tmp/composed.mp3",
			"duration_seconds": 182.5,
		}

		from src.tasks.callbacks import on_composition_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_composition_complete, result=result, episode_id=episode_id)

		assert episode.file_path == "/tmp/composed.mp3"
		assert episode.generation_status == "composing"
		progress = episode.generation_progress
		assert progress.get("composition") == "complete"
		assert progress.get("duration_seconds") == 182.5
		mock_session.commit.assert_called_once()

	def test_skips_update_when_composition_failed(self):
		"""No database update happens when result status is not 'success'."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {"status": "failed", "error": "merge error"}

		from src.tasks.callbacks import on_composition_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_composition_complete, result=result, episode_id=episode_id)

		mock_ctx.__enter__.assert_not_called()


# ---------------------------------------------------------------------------
# on_distribution_complete
# ---------------------------------------------------------------------------

class TestOnDistributionComplete:
	"""Tests for the platform distribution success callback."""

	def test_updates_distribution_progress(self):
		"""Distribution result is stored in generation_progress['distribution']."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_abc123",
			"platform_url": None,
		}

		from src.tasks.callbacks import on_distribution_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(
				on_distribution_complete,
				result=result,
				episode_id=episode_id,
				platform="spotify",
			)

		progress = episode.generation_progress
		assert "distribution" in progress
		spotify_entry = progress["distribution"]["spotify"]
		assert spotify_entry["status"] == "complete"
		assert spotify_entry["platform_episode_id"] == "sp_abc123"
		assert episode.generation_status == "distributing"
		mock_session.commit.assert_called_once()

	def test_accumulates_multiple_platforms(self):
		"""Calling the callback twice for different platforms accumulates results."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		# First call sets spotify
		episode.generation_progress = {}

		mock_ctx1, mock_session1 = _make_sync_session(episode)
		mock_ctx2, mock_session2 = _make_sync_session(episode)

		spotify_result = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "sp_id",
			"platform_url": None,
		}
		apple_result = {
			"status": "success",
			"platform": "apple_podcasts",
			"platform_episode_id": "ap_id",
			"platform_url": None,
		}

		from src.tasks.callbacks import on_distribution_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", side_effect=[mock_ctx1, mock_ctx2]):
			_invoke_task(
				on_distribution_complete,
				result=spotify_result,
				episode_id=episode_id,
				platform="spotify",
			)
			_invoke_task(
				on_distribution_complete,
				result=apple_result,
				episode_id=episode_id,
				platform="apple_podcasts",
			)

		assert "spotify" in episode.generation_progress["distribution"]
		assert "apple_podcasts" in episode.generation_progress["distribution"]

	def test_skips_update_on_failure_result(self):
		"""No database update when result indicates failure."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		result = {"status": "failed", "error": "auth failed"}

		from src.tasks.callbacks import on_distribution_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(
				on_distribution_complete,
				result=result,
				episode_id=episode_id,
				platform="spotify",
			)

		mock_ctx.__enter__.assert_not_called()


# ---------------------------------------------------------------------------
# on_workflow_complete
# ---------------------------------------------------------------------------

class TestOnWorkflowComplete:
	"""Tests for the final workflow success callback."""

	def test_marks_episode_complete(self):
		"""Episode.generation_status is set to 'complete'."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		from src.tasks.callbacks import on_workflow_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_workflow_complete, result={}, episode_id=episode_id)

		assert episode.generation_status == "complete"
		progress = episode.generation_progress
		assert progress.get("status") == "complete"
		assert "completed_at" in progress
		mock_session.commit.assert_called_once()

	def test_handles_missing_episode(self):
		"""Callback does not raise when episode is not found."""
		episode_id = str(uuid.uuid4())
		mock_ctx, mock_session = _make_sync_session(None)

		from src.tasks.callbacks import on_workflow_complete

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(on_workflow_complete, result={}, episode_id=episode_id)

		mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# on_workflow_failure
# ---------------------------------------------------------------------------

class TestOnWorkflowFailure:
	"""Tests for the workflow error callback."""

	def test_marks_episode_failed(self):
		"""Episode.generation_status is set to 'failed' with error details."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		from src.tasks.callbacks import on_workflow_failure

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(
				on_workflow_failure,
				task_id="task-abc",
				exc=ValueError("S3 credentials missing"),
				traceback="Traceback ...",
				episode_id=episode_id,
				task_name="upload_to_s3",
			)

		assert episode.generation_status == "failed"
		progress = episode.generation_progress
		assert progress.get("status") == "failed"
		assert progress.get("failed_task") == "upload_to_s3"
		assert "upload_to_s3" in progress.get("error_message", "")
		assert "failed_at" in progress
		mock_session.commit.assert_called_once()

	def test_uses_unknown_when_task_name_omitted(self):
		"""task_name defaults to 'unknown' when not provided."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		from src.tasks.callbacks import on_workflow_failure

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(
				on_workflow_failure,
				task_id="task-xyz",
				exc=RuntimeError("boom"),
				traceback="...",
				episode_id=episode_id,
				# task_name omitted → default 'unknown'
			)

		assert episode.generation_progress.get("failed_task") == "unknown"

	def test_handles_missing_episode(self):
		"""Callback does not raise when episode is not found."""
		episode_id = str(uuid.uuid4())
		mock_ctx, mock_session = _make_sync_session(None)

		from src.tasks.callbacks import on_workflow_failure

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_invoke_task(
				on_workflow_failure,
				task_id="t",
				exc=Exception("x"),
				traceback="",
				episode_id=episode_id,
				task_name="upload_to_s3",
			)

		mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# build_generation_workflow
# ---------------------------------------------------------------------------

class TestBuildGenerationWorkflow:
	"""Tests for the workflow builder function."""

	def test_returns_chain_object(self):
		"""build_generation_workflow returns a Celery chain."""
		from celery import chain as celery_chain
		from src.tasks.podcast_generation import build_generation_workflow

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "test-bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=str(uuid.uuid4()),
				audio_file_path="/tmp/podcast.mp3",
			)

		assert isinstance(workflow, celery_chain)

	def test_upload_task_included_by_default(self):
		"""The upload_to_s3 task signature is always the first in the chain."""
		from src.tasks.podcast_generation import build_generation_workflow

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "my-bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=str(uuid.uuid4()),
				audio_file_path="/tmp/audio.mp3",
			)

		# The chain tasks list contains at least the upload task signature
		task_names = [t.task for t in workflow.tasks]
		assert "upload_to_s3" in task_names

	def test_composition_task_included_when_enabled(self):
		"""merge_audio_snippets task is in the chain when enable_composition=True."""
		from src.tasks.podcast_generation import build_generation_workflow

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=str(uuid.uuid4()),
				audio_file_path="/tmp/a.mp3",
				enable_composition=True,
				composition_timeline=[],
			)

		task_names = [t.task for t in workflow.tasks]
		assert "merge_audio_snippets" in task_names

	def test_composition_task_excluded_by_default(self):
		"""merge_audio_snippets is NOT in the chain when enable_composition=False."""
		from src.tasks.podcast_generation import build_generation_workflow

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=str(uuid.uuid4()),
				audio_file_path="/tmp/a.mp3",
				enable_composition=False,
			)

		task_names = [t.task for t in workflow.tasks]
		assert "merge_audio_snippets" not in task_names

	def test_distribution_tasks_included_when_enabled(self):
		"""distribute_to_platform tasks appear when enable_distribution=True."""
		from src.tasks.podcast_generation import build_generation_workflow

		platforms = {
			"spotify": {"oauth_tokens": {}},
			"webhook": {"url": "https://example.com/hook"},
		}

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=str(uuid.uuid4()),
				audio_file_path="/tmp/a.mp3",
				enable_distribution=True,
				platforms=platforms,
			)

		task_names = [t.task for t in workflow.tasks]
		assert task_names.count("distribute_to_platform") == 2

	def test_s3_bucket_uses_provided_value(self):
		"""Explicit s3_bucket overrides settings.AWS_S3_BUCKET."""
		from src.tasks.podcast_generation import build_generation_workflow

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "default-bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=str(uuid.uuid4()),
				audio_file_path="/tmp/a.mp3",
				s3_bucket="override-bucket",
			)

		# The upload task's kwargs should use the override bucket
		upload_task = workflow.tasks[0]
		assert upload_task.kwargs.get("bucket_name") == "override-bucket"

	def test_s3_key_contains_episode_id(self):
		"""The generated S3 key includes the episode_id for uniqueness."""
		from src.tasks.podcast_generation import build_generation_workflow

		episode_id = str(uuid.uuid4())

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "bucket"
			workflow = build_generation_workflow(
				user_id="test-user-id",
				episode_id=episode_id,
				audio_file_path="/tmp/a.mp3",
			)

		upload_task = workflow.tasks[0]
		s3_key = upload_task.kwargs.get("s3_key", "")
		assert episode_id in s3_key


# ---------------------------------------------------------------------------
# _update_episode helper (internal)
# ---------------------------------------------------------------------------

class TestUpdateEpisodeHelper:
	"""Tests for the _update_episode internal helper."""

	def test_applies_column_updates(self):
		"""_update_episode sets attributes specified in updates dict."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		mock_ctx, mock_session = _make_sync_session(episode)

		from src.tasks.callbacks import _update_episode

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			result = _update_episode(
				episode_id,
				updates={"generation_status": "uploading", "s3_url": "https://x.com/f.mp3"},
			)

		assert result is True
		assert episode.generation_status == "uploading"
		assert episode.s3_url == "https://x.com/f.mp3"

	def test_merges_progress_updates(self):
		"""progress_updates are merged into existing generation_progress."""
		episode_id = str(uuid.uuid4())
		episode = _mock_episode(episode_id)
		episode.generation_progress = {"existing_key": "existing_value"}
		mock_ctx, mock_session = _make_sync_session(episode)

		from src.tasks.callbacks import _update_episode

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			_update_episode(
				episode_id,
				updates={},
				progress_updates={"new_key": "new_value"},
			)

		assert episode.generation_progress.get("existing_key") == "existing_value"
		assert episode.generation_progress.get("new_key") == "new_value"

	def test_returns_false_for_missing_episode(self):
		"""Returns False when episode is not found."""
		episode_id = str(uuid.uuid4())
		mock_ctx, mock_session = _make_sync_session(None)

		from src.tasks.callbacks import _update_episode

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			result = _update_episode(episode_id, updates={"generation_status": "failed"})

		assert result is False
		mock_session.commit.assert_not_called()

	def test_returns_false_on_db_exception(self):
		"""Returns False (does not re-raise) when a DB exception occurs."""
		episode_id = str(uuid.uuid4())
		mock_ctx = MagicMock()
		mock_ctx.__enter__ = MagicMock(side_effect=RuntimeError("connection lost"))
		mock_ctx.__exit__ = MagicMock(return_value=False)

		from src.tasks.callbacks import _update_episode

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=mock_ctx):
			result = _update_episode(episode_id, updates={})

		assert result is False
