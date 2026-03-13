"""
Tests for the Celery workflow chain integration (GAP-026).

Covers:
- build_workflow_chain() builds the correct task sequence
- Optional composition and distribution stages are included/excluded correctly
- Multiple platforms produce one distribute_to_platform_task per platform
- Workflow callbacks update Episode status in the database
- generate_podcast_task accepts and passes workflow parameters
"""

import inspect
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.tasks.podcast_generation import build_workflow_chain, generate_podcast_task
from src.tasks.workflow_callbacks import (
	update_episode_on_success,
	update_episode_on_failure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_episode(episode_id: str, status: str = "generating") -> MagicMock:
	"""Return a MagicMock that mimics an Episode ORM object."""
	ep = MagicMock()
	ep.id = uuid.UUID(episode_id)
	ep.generation_status = status
	ep.generation_progress = {}
	ep.error_message = None
	ep.file_path = None
	ep.transcript_path = None
	ep.duration_seconds = None
	ep.file_size_bytes = None
	ep.s3_url = None
	ep.s3_key = None
	ep.platform_ids = {}
	return ep


EPISODE_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 1. build_workflow_chain — task sequence
# ---------------------------------------------------------------------------

class TestBuildWorkflowChain:

	def _chain_task_names(self, tasks_list) -> list:
		"""Extract the task name from each Celery signature in the chain tasks list."""
		names = []
		for sig in tasks_list:
			# In Celery, Signature.task holds the task *name* as a string
			task = getattr(sig, "task", None) or getattr(sig, "type", None)
			if isinstance(task, str):
				names.append(task)
			elif task is not None:
				names.append(getattr(task, "name", str(task)))
			else:
				names.append(str(sig))
		return names

	def test_upload_always_included(self):
		"""S3 upload task is always the first task in the chain."""
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path="/tmp/ep_transcript.txt",
			duration_seconds=120.0,
			file_size_bytes=1024,
		)
		tasks = list(wf.tasks)
		assert len(tasks) >= 2  # at least upload + success callback
		task_names = self._chain_task_names(tasks)
		assert "upload_to_s3" in task_names[0]

	def test_success_callback_always_appended(self):
		"""update_episode_on_success is always the last task in the chain."""
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
		)
		tasks = list(wf.tasks)
		task_names = self._chain_task_names(tasks)
		assert "update_episode_on_success" in task_names[-1]

	def test_composition_excluded_by_default(self):
		"""merge_audio_snippets_task is absent when enable_composition=False."""
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
			enable_composition=False,
		)
		task_names = self._chain_task_names(list(wf.tasks))
		assert not any("merge_audio_snippets" in n for n in task_names)

	def test_composition_included_when_enabled(self):
		"""merge_audio_snippets_task appears when enable_composition=True."""
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
			enable_composition=True,
		)
		task_names = self._chain_task_names(list(wf.tasks))
		assert any("merge_audio_snippets" in n for n in task_names)

	def test_distribution_excluded_by_default(self):
		"""distribute_to_platform_task is absent when enable_distribution=False."""
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
			enable_distribution=False,
		)
		task_names = self._chain_task_names(list(wf.tasks))
		assert not any("distribute_to_platform" in n for n in task_names)

	def test_distribution_excluded_without_platforms(self):
		"""distribute_to_platform_task absent when enable_distribution=True but no platforms."""
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
			enable_distribution=True,
			platforms={},
		)
		task_names = self._chain_task_names(list(wf.tasks))
		assert not any("distribute_to_platform" in n for n in task_names)

	def test_distribution_included_per_platform(self):
		"""One distribute_to_platform_task per platform when distribution enabled."""
		platforms = {
			"spotify": {"api_key": "key1"},
			"apple_podcasts": {"api_key": "key2"},
		}
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
			enable_distribution=True,
			platforms=platforms,
		)
		task_names = self._chain_task_names(list(wf.tasks))
		dist_tasks = [n for n in task_names if "distribute_to_platform" in n]
		assert len(dist_tasks) == 2

	def test_full_chain_order(self):
		"""Full chain: upload → composition → distribution → success callback."""
		platforms = {"spotify": {"api_key": "k"}}
		wf = build_workflow_chain(
			episode_id=EPISODE_ID,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
			enable_composition=True,
			enable_distribution=True,
			platforms=platforms,
		)
		task_names = self._chain_task_names(list(wf.tasks))
		# Validate ordering
		upload_idx = next(i for i, n in enumerate(task_names) if "upload_to_s3" in n)
		compose_idx = next(i for i, n in enumerate(task_names) if "merge_audio_snippets" in n)
		dist_idx = next(i for i, n in enumerate(task_names) if "distribute_to_platform" in n)
		success_idx = next(i for i, n in enumerate(task_names) if "update_episode_on_success" in n)

		assert upload_idx < compose_idx < dist_idx < success_idx

	def test_chain_uses_s3_key_with_episode_id(self):
		"""S3 key in the upload signature contains the episode_id."""
		ep_id = str(uuid.uuid4())
		wf = build_workflow_chain(
			episode_id=ep_id,
			audio_file_path="/tmp/ep.mp3",
			transcript_path=None,
			duration_seconds=0,
			file_size_bytes=0,
		)
		upload_sig = list(wf.tasks)[0]
		upload_kwargs = upload_sig.kwargs
		assert ep_id in upload_kwargs.get("s3_key", "")


# ---------------------------------------------------------------------------
# 2. generate_podcast_task — signature / new parameters
# ---------------------------------------------------------------------------

class TestGeneratePodcastTaskSignature:

	def test_accepts_enable_composition(self):
		sig = inspect.signature(generate_podcast_task.run)
		assert "enable_composition" in sig.parameters

	def test_accepts_enable_distribution(self):
		sig = inspect.signature(generate_podcast_task.run)
		assert "enable_distribution" in sig.parameters

	def test_accepts_platforms(self):
		sig = inspect.signature(generate_podcast_task.run)
		assert "platforms" in sig.parameters

	def test_enable_composition_defaults_false(self):
		sig = inspect.signature(generate_podcast_task.run)
		assert sig.parameters["enable_composition"].default is False

	def test_enable_distribution_defaults_false(self):
		sig = inspect.signature(generate_podcast_task.run)
		assert sig.parameters["enable_distribution"].default is False

	def test_platforms_defaults_none(self):
		sig = inspect.signature(generate_podcast_task.run)
		assert sig.parameters["platforms"].default is None


# ---------------------------------------------------------------------------
# 3. generate_podcast_task — workflow dispatch
# ---------------------------------------------------------------------------


def _mock_podcastfy_modules():
	mock_client = MagicMock()
	mock_podcastfy = types.ModuleType("podcastfy")
	mock_podcastfy.client = mock_client
	return mock_client, {
		"podcastfy": mock_podcastfy,
		"podcastfy.client": mock_client,
	}


class TestGeneratePodcastTaskWorkflowDispatch:

	def _run_with_mocks(self, extra_kwargs=None, mock_gen_return="/tmp/out.mp3"):
		"""Helper: run generate_podcast_task.run() with all heavy deps mocked."""
		ep_id = str(uuid.uuid4())
		mock_client, mock_modules = _mock_podcastfy_modules()
		mock_client.generate_podcast = MagicMock(return_value=mock_gen_return)
		audio_instance = MagicMock()
		audio_instance.__len__ = MagicMock(return_value=60000)

		kwargs = {"episode_id": ep_id, "urls": ["https://example.com"]}
		if extra_kwargs:
			kwargs.update(extra_kwargs)

		with patch.object(generate_podcast_task, "update_state"), \
			 patch.dict(sys.modules, mock_modules), \
			 patch("src.tasks.podcast_generation.os.path.getsize", return_value=512), \
			 patch("src.tasks.podcast_generation.AudioSegment") as mock_audio, \
			 patch("src.tasks.podcast_generation.finalize_episode_generation_task") as mock_fin, \
			 patch("src.tasks.podcast_generation.build_workflow_chain") as mock_bwc, \
			 patch("src.tasks.podcast_generation.update_episode_on_failure"):

			mock_audio.from_file.return_value = audio_instance
			mock_chain = MagicMock()
			mock_bwc.return_value = mock_chain

			result = generate_podcast_task.run(**kwargs)

		return result, mock_fin, mock_bwc, mock_chain

	def test_default_uses_finalize_task(self):
		"""Without workflow flags, finalize_episode_generation_task.delay() is called."""
		_, mock_fin, mock_bwc, _ = self._run_with_mocks()
		mock_fin.delay.assert_called_once()
		mock_bwc.assert_not_called()

	def test_composition_flag_triggers_workflow_chain(self):
		"""enable_composition=True uses build_workflow_chain instead of finalize."""
		_, mock_fin, mock_bwc, mock_chain = self._run_with_mocks(
			extra_kwargs={"enable_composition": True}
		)
		mock_bwc.assert_called_once()
		mock_chain.apply_async.assert_called_once()
		mock_fin.delay.assert_not_called()

	def test_distribution_flag_triggers_workflow_chain(self):
		"""enable_distribution=True uses build_workflow_chain."""
		platforms = {"spotify": {"api_key": "k"}}
		_, mock_fin, mock_bwc, mock_chain = self._run_with_mocks(
			extra_kwargs={"enable_distribution": True, "platforms": platforms}
		)
		mock_bwc.assert_called_once()
		mock_chain.apply_async.assert_called_once()
		mock_fin.delay.assert_not_called()

	def test_build_workflow_chain_receives_correct_args(self):
		"""build_workflow_chain is called with the right episode and file args."""
		ep_id = str(uuid.uuid4())
		mock_client, mock_modules = _mock_podcastfy_modules()
		mock_client.generate_podcast = MagicMock(return_value="/tmp/podcast.mp3")
		audio_instance = MagicMock()
		audio_instance.__len__ = MagicMock(return_value=90000)

		with patch.object(generate_podcast_task, "update_state"), \
			 patch.dict(sys.modules, mock_modules), \
			 patch("src.tasks.podcast_generation.os.path.getsize", return_value=2048), \
			 patch("src.tasks.podcast_generation.AudioSegment") as mock_audio, \
			 patch("src.tasks.podcast_generation.finalize_episode_generation_task"), \
			 patch("src.tasks.podcast_generation.build_workflow_chain") as mock_bwc, \
			 patch("src.tasks.podcast_generation.update_episode_on_failure"):

			mock_audio.from_file.return_value = audio_instance
			mock_bwc.return_value = MagicMock()

			generate_podcast_task.run(
				episode_id=ep_id,
				urls=["https://example.com"],
				enable_composition=True,
			)

		call_kwargs = mock_bwc.call_args.kwargs
		assert call_kwargs["episode_id"] == ep_id
		assert call_kwargs["audio_file_path"] == "/tmp/podcast.mp3"
		assert call_kwargs["duration_seconds"] == pytest.approx(90.0)
		assert call_kwargs["file_size_bytes"] == 2048
		assert call_kwargs["enable_composition"] is True

	def test_result_still_returned_with_workflow_chain(self):
		"""generate_podcast_task still returns success dict when using workflow chain."""
		result, _, _, _ = self._run_with_mocks(
			extra_kwargs={"enable_composition": True}
		)
		assert result["status"] == "success"
		assert result["audio_file_path"] == "/tmp/out.mp3"


# ---------------------------------------------------------------------------
# 4. update_episode_on_success
# ---------------------------------------------------------------------------

class TestUpdateEpisodeOnSuccess:

	def test_marks_episode_complete_and_sets_s3_url(self):
		"""On success, episode.generation_status becomes 'complete' with s3_url."""
		ep_id = str(uuid.uuid4())
		episode = _make_episode(ep_id)

		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = episode

		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db), \
			 patch("src.tasks.workflow_callbacks.settings") as mock_settings:
			mock_settings.AWS_REGION = "us-east-1"

			result = update_episode_on_success.run(
				episode_id=ep_id,
				audio_file_path="/tmp/ep.mp3",
				transcript_path="/tmp/ep_transcript.txt",
				duration_seconds=120.0,
				file_size_bytes=2048,
				s3_key="podcasts/episode-123/podcast.mp3",
				bucket_name="my-bucket",
			)

		assert result["status"] == "success"
		assert episode.generation_status == "complete"
		assert episode.s3_url == "https://my-bucket.s3.amazonaws.com/podcasts/episode-123/podcast.mp3"
		assert episode.file_path == "/tmp/ep.mp3"
		assert episode.transcript_path == "/tmp/ep_transcript.txt"
		assert episode.duration_seconds == 120.0
		assert episode.file_size_bytes == 2048
		mock_db.commit.assert_called_once()

	def test_returns_failed_when_episode_not_found(self):
		"""Returns failed dict when episode is missing from the database."""
		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = None

		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db):
			result = update_episode_on_success.run(episode_id=str(uuid.uuid4()))

		assert result["status"] == "failed"
		assert "not found" in result["error"].lower()

	def test_s3_url_none_when_no_key(self):
		"""s3_url is None when s3_key is not provided."""
		ep_id = str(uuid.uuid4())
		episode = _make_episode(ep_id)

		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = episode

		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db):
			result = update_episode_on_success.run(episode_id=ep_id)

		assert episode.s3_url is None
		assert result["status"] == "success"

	def test_s3_url_uses_region_subdomain_for_non_us_east(self):
		"""S3 URL includes region subdomain for non-us-east-1 regions."""
		ep_id = str(uuid.uuid4())
		episode = _make_episode(ep_id)

		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = episode

		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db), \
			 patch("src.tasks.workflow_callbacks.settings") as mock_settings:
			mock_settings.AWS_REGION = "eu-west-1"

			update_episode_on_success.run(
				episode_id=ep_id,
				s3_key="ep/podcast.mp3",
				bucket_name="bucket",
			)

		assert "eu-west-1" in episode.s3_url


# ---------------------------------------------------------------------------
# 5. update_episode_on_failure
# ---------------------------------------------------------------------------

class TestUpdateEpisodeOnFailure:

	def test_marks_episode_failed_with_error_message(self):
		"""On failure, episode.generation_status becomes 'failed' with error_message."""
		ep_id = str(uuid.uuid4())
		episode = _make_episode(ep_id)

		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = episode

		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db):
			result = update_episode_on_failure.run(
				episode_id=ep_id,
				error="S3 upload failed: bucket not found",
			)

		assert result["status"] == "failed"
		assert episode.generation_status == "failed"
		assert episode.error_message == "S3 upload failed: bucket not found"
		mock_db.commit.assert_called_once()

	def test_returns_failed_when_episode_not_found(self):
		"""Returns failed dict when episode is missing from the database."""
		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = None

		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db):
			result = update_episode_on_failure.run(
				episode_id=str(uuid.uuid4()),
				error="Something went wrong",
			)

		assert result["status"] == "failed"
		assert "not found" in result["error"].lower()

	def test_error_message_stored_in_progress(self):
		"""Error message is persisted in generation_progress dict."""
		ep_id = str(uuid.uuid4())
		episode = _make_episode(ep_id)

		mock_db = MagicMock()
		mock_db.__enter__ = MagicMock(return_value=mock_db)
		mock_db.__exit__ = MagicMock(return_value=False)
		mock_db.get.return_value = episode

		error_msg = "Audio composition crashed"
		with patch("src.tasks.workflow_callbacks.SyncSessionLocal", return_value=mock_db):
			update_episode_on_failure.run(episode_id=ep_id, error=error_msg)

		assert episode.generation_progress.get("error_message") == error_msg
		assert episode.generation_progress.get("stage") == "failed"
