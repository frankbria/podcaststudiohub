"""
Unit tests for Celery task chaining callbacks (issue #35 / GAP-028).

Tests cover:
- on_upload_complete: updates Episode.s3_url and status
- on_composition_complete: updates Episode.file_path and progress
- on_distribution_complete: updates Episode.generation_progress with platform IDs
- on_workflow_complete: marks Episode as complete
- on_workflow_failure: marks Episode as failed with error details
- build_generation_workflow: constructs Celery chain with callbacks
"""

import uuid
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_episode(episode_id=None, status="generating", progress=None):
	"""Return a MagicMock that mimics an Episode model instance."""
	ep = MagicMock()
	ep.id = uuid.UUID(episode_id) if episode_id else uuid.uuid4()
	ep.generation_status = status
	ep.generation_progress = progress or {}
	ep.s3_url = None
	ep.s3_key = None
	ep.file_path = None
	return ep


def _make_db_session(episode):
	"""Return a context-manager mock that yields a session with get() → episode."""
	session = MagicMock()
	session.get.return_value = episode
	session.commit = MagicMock()

	ctx = MagicMock()
	ctx.__enter__ = MagicMock(return_value=session)
	ctx.__exit__ = MagicMock(return_value=False)
	return ctx, session


# ---------------------------------------------------------------------------
# on_upload_complete
# ---------------------------------------------------------------------------

class TestOnUploadComplete:

	def test_success_updates_s3_url_and_status(self):
		"""Successful upload result → Episode.s3_url, s3_key updated and status set."""
		from src.tasks.callbacks import on_upload_complete

		episode_id = str(uuid.uuid4())
		episode = _make_episode(episode_id=episode_id)
		ctx, session = _make_db_session(episode)

		result = {
			"status": "success",
			"s3_url": "https://bucket.s3.amazonaws.com/key.mp3",
			"s3_key": "podcasts/user-1/episode-1.mp3",
			"file_size_bytes": 5000,
		}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_upload_complete.run(result=result, episode_id=episode_id)

		assert episode.s3_url == result["s3_url"]
		assert episode.s3_key == result["s3_key"]
		assert episode.generation_status == "uploading"
		session.commit.assert_called_once()

	def test_failed_result_skips_db_update(self):
		"""A result with status != 'success' → no DB update, just logs."""
		from src.tasks.callbacks import on_upload_complete

		episode_id = str(uuid.uuid4())
		ctx, session = _make_db_session(_make_episode(episode_id=episode_id))

		result = {"status": "failed", "error": "S3 error", "s3_url": None, "s3_key": None}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_upload_complete.run(result=result, episode_id=episode_id)

		session.commit.assert_not_called()

	def test_missing_episode_logs_and_returns(self):
		"""If episode not found in DB, logs error and returns without error."""
		from src.tasks.callbacks import on_upload_complete

		episode_id = str(uuid.uuid4())
		session = MagicMock()
		session.get.return_value = None  # episode not found
		ctx = MagicMock()
		ctx.__enter__ = MagicMock(return_value=session)
		ctx.__exit__ = MagicMock(return_value=False)

		result = {"status": "success", "s3_url": "https://url", "s3_key": "key"}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			# Should not raise
			on_upload_complete.run(result=result, episode_id=episode_id)

		session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# on_composition_complete
# ---------------------------------------------------------------------------

class TestOnCompositionComplete:

	def test_success_updates_file_path_and_progress(self):
		"""Successful composition → Episode.file_path updated with progress recorded."""
		from src.tasks.callbacks import on_composition_complete

		episode_id = str(uuid.uuid4())
		episode = _make_episode(episode_id=episode_id)
		ctx, session = _make_db_session(episode)

		result = {
			"status": "success",
			"output_path": "/tmp/composed_audio.mp3",
			"duration_seconds": 120.5,
			"file_size_bytes": 9000,
		}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_composition_complete.run(result=result, episode_id=episode_id)

		assert episode.file_path == result["output_path"]
		assert episode.generation_status == "composing"
		assert episode.generation_progress.get("composition") == "complete"
		assert episode.generation_progress.get("duration_seconds") == result["duration_seconds"]
		session.commit.assert_called_once()

	def test_failed_result_skips_db_update(self):
		"""Failed composition result → no DB update."""
		from src.tasks.callbacks import on_composition_complete

		episode_id = str(uuid.uuid4())
		ctx, session = _make_db_session(_make_episode(episode_id=episode_id))

		result = {"status": "failed", "error": "pydub crashed", "output_path": None}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_composition_complete.run(result=result, episode_id=episode_id)

		session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# on_distribution_complete
# ---------------------------------------------------------------------------

class TestOnDistributionComplete:

	def test_success_updates_generation_progress_with_platform_id(self):
		"""Successful distribution → platform ID stored in generation_progress."""
		from src.tasks.callbacks import on_distribution_complete

		episode_id = str(uuid.uuid4())
		episode = _make_episode(episode_id=episode_id, progress={})
		ctx, session = _make_db_session(episode)

		result = {
			"status": "success",
			"platform": "spotify",
			"platform_episode_id": "spot-123",
			"platform_url": None,
		}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_distribution_complete.run(
				result=result, episode_id=episode_id, platform="spotify"
			)

		dist = episode.generation_progress.get("distribution", {})
		assert dist.get("spotify") == "spot-123"
		session.commit.assert_called_once()

	def test_multiple_platforms_accumulate_in_progress(self):
		"""Distribution results for multiple platforms are accumulated, not overwritten."""
		from src.tasks.callbacks import on_distribution_complete

		episode_id = str(uuid.uuid4())
		# Pre-existing progress with spotify already done
		existing_progress = {"distribution": {"spotify": "spot-123"}}
		episode = _make_episode(episode_id=episode_id, progress=existing_progress)
		ctx, session = _make_db_session(episode)

		result = {
			"status": "success",
			"platform": "apple_podcasts",
			"platform_episode_id": "apple-456",
		}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_distribution_complete.run(
				result=result, episode_id=episode_id, platform="apple_podcasts"
			)

		dist = episode.generation_progress["distribution"]
		assert dist["spotify"] == "spot-123"
		assert dist["apple_podcasts"] == "apple-456"

	def test_failed_result_skips_update(self):
		"""Failed distribution → no DB update."""
		from src.tasks.callbacks import on_distribution_complete

		episode_id = str(uuid.uuid4())
		ctx, session = _make_db_session(_make_episode(episode_id=episode_id))

		result = {"status": "failed", "error": "API error", "platform_episode_id": None}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_distribution_complete.run(
				result=result, episode_id=episode_id, platform="spotify"
			)

		session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# on_workflow_complete
# ---------------------------------------------------------------------------

class TestOnWorkflowComplete:

	def test_marks_episode_as_complete(self):
		"""Workflow complete → Episode.generation_status = 'complete'."""
		from src.tasks.callbacks import on_workflow_complete

		episode_id = str(uuid.uuid4())
		episode = _make_episode(episode_id=episode_id, status="uploading")
		ctx, session = _make_db_session(episode)

		result = {"status": "success", "episode_id": episode_id}

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_workflow_complete.run(result=result, episode_id=episode_id)

		assert episode.generation_status == "complete"
		assert episode.generation_progress.get("status") == "published"
		session.commit.assert_called_once()

	def test_missing_episode_does_not_raise(self):
		"""Missing episode in DB → logs error, does not raise."""
		from src.tasks.callbacks import on_workflow_complete

		episode_id = str(uuid.uuid4())
		session = MagicMock()
		session.get.return_value = None
		ctx = MagicMock()
		ctx.__enter__ = MagicMock(return_value=session)
		ctx.__exit__ = MagicMock(return_value=False)

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_workflow_complete.run(result={}, episode_id=episode_id)

		session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# on_workflow_failure
# ---------------------------------------------------------------------------

class TestOnWorkflowFailure:

	def test_marks_episode_as_failed_with_error_details(self):
		"""Failure callback → Episode.generation_status = 'failed' with error info."""
		from src.tasks.callbacks import on_workflow_failure

		episode_id = str(uuid.uuid4())
		episode = _make_episode(episode_id=episode_id, status="generating")
		ctx, session = _make_db_session(episode)

		failed_task_id = "some-celery-task-id"

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_workflow_failure.run(
				task_id=failed_task_id,
				episode_id=episode_id,
				task_name="upload_to_s3",
			)

		assert episode.generation_status == "failed"
		assert episode.generation_progress.get("status") == "failed"
		assert episode.generation_progress.get("failed_task") == "upload_to_s3"
		session.commit.assert_called_once()

	def test_unknown_task_name_still_marks_failed(self):
		"""task_name is optional — episode still marked failed without it."""
		from src.tasks.callbacks import on_workflow_failure

		episode_id = str(uuid.uuid4())
		episode = _make_episode(episode_id=episode_id)
		ctx, session = _make_db_session(episode)

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_workflow_failure.run(
				task_id="tid-1",
				episode_id=episode_id,
				task_name=None,
			)

		assert episode.generation_status == "failed"

	def test_missing_episode_does_not_raise(self):
		"""Missing episode → logs error gracefully."""
		from src.tasks.callbacks import on_workflow_failure

		episode_id = str(uuid.uuid4())
		session = MagicMock()
		session.get.return_value = None
		ctx = MagicMock()
		ctx.__enter__ = MagicMock(return_value=session)
		ctx.__exit__ = MagicMock(return_value=False)

		with patch("src.tasks.callbacks.SyncSessionLocal", return_value=ctx):
			on_workflow_failure.run(
				task_id="tid-2",
				episode_id=episode_id,
				task_name="merge_audio_snippets",
			)

		session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# build_generation_workflow
# ---------------------------------------------------------------------------

class TestBuildGenerationWorkflow:

	def test_returns_celery_chain(self):
		"""build_generation_workflow returns a Celery chain object."""
		from src.tasks.podcast_generation import build_generation_workflow

		episode_id = str(uuid.uuid4())
		audio_file_path = "/tmp/podcast.mp3"

		workflow = build_generation_workflow(
			episode_id=episode_id,
			audio_file_path=audio_file_path,
		)

		# Must be a Celery chain (or canvas) — it has a __or__ operator / tasks attr
		assert hasattr(workflow, "tasks") or hasattr(workflow, "__or__")

	def test_chain_includes_upload_task_when_bucket_configured(self):
		"""When AWS_S3_BUCKET is set, the workflow includes upload_to_s3_task."""
		from src.tasks.podcast_generation import build_generation_workflow

		episode_id = str(uuid.uuid4())

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "my-bucket"
			mock_settings.AWS_REGION = "us-east-1"

			workflow = build_generation_workflow(
				episode_id=episode_id,
				audio_file_path="/tmp/audio.mp3",
			)

		# Inspect task names inside the chain
		task_names = [t.task for t in workflow.tasks]
		assert "upload_to_s3" in task_names

	def test_chain_skips_upload_when_no_bucket(self):
		"""When AWS_S3_BUCKET is empty, the workflow skips upload_to_s3_task."""
		from src.tasks.podcast_generation import build_generation_workflow

		episode_id = str(uuid.uuid4())

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = ""

			workflow = build_generation_workflow(
				episode_id=episode_id,
				audio_file_path="/tmp/audio.mp3",
			)

		task_names = [t.task for t in workflow.tasks]
		assert "upload_to_s3" not in task_names
		# Still has the workflow_complete callback
		assert "on_workflow_complete" in task_names

	def test_chain_includes_composition_when_enabled(self):
		"""With enable_composition=True, the chain includes merge_audio_snippets."""
		from src.tasks.podcast_generation import build_generation_workflow

		episode_id = str(uuid.uuid4())

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = ""

			workflow = build_generation_workflow(
				episode_id=episode_id,
				audio_file_path="/tmp/audio.mp3",
				enable_composition=True,
				timeline=[{"file_path": "/tmp/seg.mp3"}],
				output_path="/tmp/out.mp3",
			)

		task_names = [t.task for t in workflow.tasks]
		assert "merge_audio_snippets" in task_names

	def test_chain_does_not_include_composition_by_default(self):
		"""By default (enable_composition=False), composition task is not included."""
		from src.tasks.podcast_generation import build_generation_workflow

		episode_id = str(uuid.uuid4())

		with patch("src.tasks.podcast_generation.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = ""

			workflow = build_generation_workflow(
				episode_id=episode_id,
				audio_file_path="/tmp/audio.mp3",
			)

		task_names = [t.task for t in workflow.tasks]
		assert "merge_audio_snippets" not in task_names
