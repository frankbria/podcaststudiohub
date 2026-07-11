"""
Tests for podcast generation Celery task parameter handling.

Covers issue #204: the task previously called podcastfy 0.4.1's
``generate_podcast()`` with ``file=`` and ``youtube_urls=`` kwargs that do not
exist in the installed signature, so every generation failed with TypeError.

The task must only pass kwargs that exist in the real podcastfy signature:
``urls, text, image_paths, tts_model, conversation_config, longform, topic``.
YouTube URLs arrive via ``urls``; file/PDF sources arrive pre-extracted via
``text_content`` (mapped to ``text``).
"""

import inspect
import os
import shutil
import tempfile
import types
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import uuid4

from tests.module_patching import patch_modules

# Real podcastfy function — imported so tests assert against the ACTUAL
# installed signature (not a permissive MagicMock). This is the drift guard.
from podcastfy.client import generate_podcast as real_generate_podcast
from src.tasks.podcast_generation import generate_podcast_task


def _mock_podcastfy_modules(return_value: str = "/tmp/output.mp3") -> tuple[MagicMock, dict[str, Any]]:
	"""Return mocked podcastfy client + modules dict for sys.modules patching.

	The ``generate_podcast`` attribute is an ``autospec`` of the real function,
	so passing any kwarg the real podcastfy signature does not accept raises
	TypeError — exactly the failure mode issue #204 was about. This prevents the
	false-green that plain MagicMocks produced.
	"""
	mock_client = MagicMock()
	mock_client.generate_podcast = create_autospec(
		real_generate_podcast, return_value=return_value
	)
	mock_podcastfy = types.ModuleType("podcastfy")
	mock_podcastfy.client = mock_client
	return mock_client, {
		"podcastfy": mock_podcastfy,
		"podcastfy.client": mock_client,
	}


def _run_task(**task_kwargs: Any) -> tuple[dict[str, Any], MagicMock]:
	"""Run the Celery task body with podcastfy autospec-mocked, return (result, mock_gen)."""
	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_gen = mock_client.generate_podcast

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=60000)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch_modules(mock_modules), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=1024), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance
		result = generate_podcast_task.run(**task_kwargs)

	return result, mock_gen


# ============================================================================
# PARAMETER NAME TESTS (signature inspection)
# ============================================================================

def test_task_does_not_accept_invalid_parameters():
	"""Task must not expose file_paths / youtube_urls (no valid podcastfy mapping)."""
	sig = inspect.signature(generate_podcast_task.run)
	params = list(sig.parameters.keys())
	assert 'file_paths' not in params, (
		"Task must not accept 'file_paths' — podcastfy 0.4.1 has no 'file' kwarg; "
		"file sources are pre-extracted into text_content."
	)
	assert 'youtube_urls' not in params, (
		"Task must not accept 'youtube_urls' — podcastfy 0.4.1 has no such kwarg; "
		"YouTube URLs flow through 'urls'."
	)


def test_task_accepts_text_content_parameter():
	"""Task signature must accept text_content (not text) to match router call."""
	sig = inspect.signature(generate_podcast_task.run)
	params = list(sig.parameters.keys())
	assert 'text_content' in params, (
		"Task must accept 'text_content' parameter (router sends text_content=...)"
	)
	assert 'text' not in params, (
		"Task must not use deprecated 'text' parameter"
	)


def test_task_accepts_urls_parameter():
	"""Task must accept urls (regular + YouTube URLs both flow here)."""
	sig = inspect.signature(generate_podcast_task.run)
	assert 'urls' in sig.parameters


def test_task_text_content_defaults_to_none():
	"""text_content parameter must default to None."""
	sig = inspect.signature(generate_podcast_task.run)
	assert sig.parameters['text_content'].default is None


# ============================================================================
# SIGNATURE DRIFT GUARD — kwargs the task passes must bind to the REAL podcastfy
# signature. This is the test required by issue #204's acceptance criteria.
# ============================================================================

def test_task_kwargs_bind_against_real_generate_podcast_signature():
	"""Every kwarg the task passes must be accepted by the real generate_podcast()."""
	_, mock_gen = _run_task(
		episode_id=str(uuid4()),
		urls=["https://youtube.com/watch?v=abc"],
		text_content="Pre-extracted file content.",
		topic="AI safety",
		tts_model="elevenlabs",
		longform=True,
	)

	mock_gen.assert_called_once()
	call_kwargs = mock_gen.call_args.kwargs

	# Binding against the real signature raises TypeError on any drift.
	inspect.signature(real_generate_podcast).bind(**call_kwargs)

	# Explicitly guard the two historically-wrong kwargs.
	assert 'file' not in call_kwargs
	assert 'youtube_urls' not in call_kwargs


def test_task_does_not_pass_invalid_kwargs_to_generate_podcast():
	"""Task must never pass file= or youtube_urls= to generate_podcast()."""
	_, mock_gen = _run_task(
		episode_id=str(uuid4()),
		urls=["https://example.com"],
	)
	call_kwargs = mock_gen.call_args.kwargs
	assert 'file' not in call_kwargs
	assert 'youtube_urls' not in call_kwargs
	assert 'output_dir' not in call_kwargs


# ============================================================================
# INTEGRATION: task passes parameters correctly to podcastfy CLI
# ============================================================================

def test_task_passes_text_content_to_generate_podcast():
	"""Task must pass text_content to generate_podcast() as the 'text' argument."""
	text_content = "This is the podcast content."
	_, mock_gen = _run_task(episode_id=str(uuid4()), text_content=text_content)

	mock_gen.assert_called_once()
	call_kwargs = mock_gen.call_args.kwargs
	assert call_kwargs.get('text') == text_content, (
		f"Expected text={text_content!r}, got text={call_kwargs.get('text')!r}"
	)


def test_task_passes_urls_to_generate_podcast():
	"""URLs (including YouTube) must be forwarded via the 'urls' kwarg."""
	urls = ["https://youtube.com/watch?v=abc", "https://example.com"]
	_, mock_gen = _run_task(episode_id=str(uuid4()), urls=urls)

	call_kwargs = mock_gen.call_args.kwargs
	assert call_kwargs.get('urls') == urls


def test_task_no_type_error_with_router_parameter_names():
	"""Calling task with the router's parameter names must not raise / fail."""
	result, _ = _run_task(
		episode_id=str(uuid4()),
		urls=["https://example.com"],
		text_content="Some text",
	)
	assert result["status"] == "success"


def test_task_returns_success_result():
	"""Task must return dict with status=success on successful generation."""
	mock_client, mock_modules = _mock_podcastfy_modules(return_value="/tmp/episode.mp3")

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=120000)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch_modules(mock_modules), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=2048), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance

		result = generate_podcast_task.run(
			episode_id=str(uuid4()),
			urls=["https://example.com"],
		)

	assert result["status"] == "success"
	assert result["audio_file_path"] == "/tmp/episode.mp3"
	assert result["file_size_bytes"] == 2048
	assert result["error"] is None


def test_task_returns_failed_result_on_exception():
	"""Task must return dict with status=failed after retries exhausted."""
	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_client.generate_podcast = create_autospec(
		real_generate_podcast, side_effect=RuntimeError("Podcastfy crashed")
	)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch_modules(mock_modules), \
		 patch.object(
			generate_podcast_task,
			"retry",
			side_effect=generate_podcast_task.MaxRetriesExceededError(),
		 ):

		result = generate_podcast_task.run(
			episode_id=str(uuid4()),
			urls=["https://example.com"],
		)

	assert result["status"] == "failed"
	assert "Podcastfy crashed" in result["error"]
	assert result["audio_file_path"] is None


# ============================================================================
# ISSUE #309 — transcript_path must not be fabricated; engine output must be
# routed into a per-run temp dir so post-upload cleanup can remove it.
# ============================================================================

def _engine_output_dirs(mock_gen) -> dict:
	"""Extract the output_directories the task injected into conversation_config."""
	cc = mock_gen.call_args.kwargs.get("conversation_config")
	assert cc is not None, "task must pass conversation_config to generate_podcast"
	return cc["text_to_speech"]["output_directories"]


def test_success_result_transcript_path_is_none():
	"""podcastfy never returns a transcript path when generating audio, so the
	task must persist None — not a string-substituted path to a file that does
	not exist (issue #309)."""
	result, mock_gen = _run_task(episode_id=str(uuid4()), urls=["https://example.com"])
	assert result["status"] == "success"
	assert result["transcript_path"] is None
	shutil.rmtree(_engine_output_dirs(mock_gen)["audio"], ignore_errors=True)


def test_task_routes_engine_output_to_per_run_temp_dir():
	"""Both audio and transcript output dirs must be the same per-run directory
	under the system temp root, named with the cleanup-recognized prefix."""
	_, mock_gen = _run_task(episode_id=str(uuid4()), urls=["https://example.com"])
	dirs = _engine_output_dirs(mock_gen)

	assert dirs["audio"] == dirs["transcripts"]
	run_dir = os.path.realpath(dirs["audio"])
	temp_root = os.path.realpath(tempfile.gettempdir())
	assert os.path.commonpath([temp_root, run_dir]) == temp_root
	assert os.path.basename(run_dir).startswith("podcastfy-run-")
	assert os.path.isdir(run_dir), "run dir must exist before the engine writes to it"
	shutil.rmtree(run_dir, ignore_errors=True)


def test_task_preserves_user_conversation_config():
	"""Injecting output_directories must not clobber user-provided conversation
	config keys (top-level or inside text_to_speech), nor mutate the caller's dict."""
	user_cc = {"word_count": 500, "text_to_speech": {"ending_message": "bye"}}
	_, mock_gen = _run_task(
		episode_id=str(uuid4()),
		urls=["https://example.com"],
		conversation_config=user_cc,
	)
	cc = mock_gen.call_args.kwargs["conversation_config"]
	assert cc["word_count"] == 500
	assert cc["text_to_speech"]["ending_message"] == "bye"
	assert "output_directories" in cc["text_to_speech"]
	# The caller's dict must not be mutated in place.
	assert "output_directories" not in user_cc["text_to_speech"]
	shutil.rmtree(cc["text_to_speech"]["output_directories"]["audio"], ignore_errors=True)


def test_terminal_failure_cleans_up_run_dir():
	"""When generation fails terminally, the attempt's run dir must be removed
	so failed attempts don't leak temp artifacts either."""
	run_dir = tempfile.mkdtemp(prefix="podcastfy-run-")
	try:
		mock_client, mock_modules = _mock_podcastfy_modules()
		mock_client.generate_podcast = create_autospec(
			real_generate_podcast, side_effect=RuntimeError("boom")
		)
		with patch.object(generate_podcast_task, 'update_state'), \
			 patch_modules(mock_modules), \
			 patch('src.tasks.podcast_generation.tempfile.mkdtemp', return_value=run_dir), \
			 patch.object(
				generate_podcast_task,
				"retry",
				side_effect=generate_podcast_task.MaxRetriesExceededError(),
			 ):
			result = generate_podcast_task.run(
				episode_id=str(uuid4()),
				urls=["https://example.com"],
			)
		assert result["status"] == "failed"
		assert not os.path.exists(run_dir)
	finally:
		shutil.rmtree(run_dir, ignore_errors=True)


def test_soft_timeout_cleans_up_run_dir():
	"""SoftTimeLimitExceeded is a separate terminal branch (it bypasses the
	generic except) — it must also remove the attempt's run dir."""
	from celery.exceptions import SoftTimeLimitExceeded

	run_dir = tempfile.mkdtemp(prefix="podcastfy-run-")
	try:
		mock_client, mock_modules = _mock_podcastfy_modules()
		mock_client.generate_podcast = create_autospec(
			real_generate_podcast, side_effect=SoftTimeLimitExceeded()
		)
		with patch.object(generate_podcast_task, 'update_state'), \
			 patch_modules(mock_modules), \
			 patch('src.tasks.podcast_generation.tempfile.mkdtemp', return_value=run_dir):
			result = generate_podcast_task.run(
				episode_id=str(uuid4()),
				urls=["https://example.com"],
			)
		assert result["status"] == "failed"
		assert not os.path.exists(run_dir)
	finally:
		shutil.rmtree(run_dir, ignore_errors=True)


class TestBuildPodcastS3Key:
	"""Canonical S3 key helper (issue #215)."""

	def test_format(self) -> None:
		"""The helper renders the exact canonical key for plain string inputs."""
		from src.tasks.podcast_generation import build_podcast_s3_key

		user_id = "abc-123"
		episode_id = "ep-456"
		assert (
			build_podcast_s3_key(user_id, episode_id)
			== "podcasts/user-abc-123/episode-ep-456.mp3"
		)

	def test_uuid_inputs(self) -> None:
		"""UUID-string inputs produce a tenant-prefixed, .mp3-suffixed key."""
		from src.tasks.podcast_generation import build_podcast_s3_key

		user_id = str(uuid4())
		episode_id = str(uuid4())
		key = build_podcast_s3_key(user_id, episode_id)
		assert key == f"podcasts/user-{user_id}/episode-{episode_id}.mp3"
		assert key.startswith("podcasts/user-")
		assert key.endswith(".mp3")


class TestUploadToS3WithRetries:
	"""Issue #220: the inline S3 upload in finalize_episode_generation_task
	bypasses Celery's retry, so a transient failure must be retried by the
	explicit wrapper instead of propagating on the first try."""

	def test_returns_success_first_try(self) -> None:
		"""A first-try success returns immediately without retrying or sleeping."""
		from src.tasks import podcast_generation as pg

		ok = {"status": "success", "s3_url": "u", "s3_key": "k", "error": None}
		with patch.object(pg, "upload_to_s3_task", return_value=ok) as up, \
			patch.object(pg.time, "sleep") as slept:
			result = pg._upload_to_s3_with_retries("f", "k", "b")
		assert result["status"] == "success"
		assert up.call_count == 1
		slept.assert_not_called()

	def test_retries_failed_status_then_succeeds(self) -> None:
		"""A returned status!=success is retried; a later success is returned."""
		from src.tasks import podcast_generation as pg

		fail = {"status": "failed", "error": "throttled"}
		ok = {"status": "success", "s3_url": "u", "s3_key": "k", "error": None}
		with patch.object(pg, "upload_to_s3_task", side_effect=[fail, ok]) as up, \
			patch.object(pg.time, "sleep") as slept:
			result = pg._upload_to_s3_with_retries("f", "k", "b")
		assert result["status"] == "success"
		assert up.call_count == 2
		assert slept.call_count == 1

	def test_retries_on_exception_then_succeeds(self) -> None:
		"""A raised transient error is retried; a later success is returned."""
		from src.tasks import podcast_generation as pg

		ok = {"status": "success", "s3_url": "u", "s3_key": "k", "error": None}
		with patch.object(
			pg, "upload_to_s3_task", side_effect=[ConnectionError("net"), ok]
		) as up, patch.object(pg.time, "sleep") as slept:
			result = pg._upload_to_s3_with_retries("f", "k", "b")
		assert result["status"] == "success"
		assert up.call_count == 2
		assert slept.call_count == 1

	def test_returns_failed_after_exhausting_attempts(self) -> None:
		"""Repeated failed-status results exhaust attempts and return failed."""
		from src.tasks import podcast_generation as pg

		fail = {"status": "failed", "error": "still throttled"}
		with patch.object(pg, "upload_to_s3_task", return_value=fail) as up, \
			patch.object(pg.time, "sleep") as slept:
			result = pg._upload_to_s3_with_retries("f", "k", "b", max_attempts=3)
		assert result["status"] == "failed"
		assert result["error"] == "still throttled"
		assert up.call_count == 3
		assert slept.call_count == 2  # no sleep after the final attempt

	def test_exhausts_attempts_on_repeated_exception(self) -> None:
		"""Repeated raised errors exhaust attempts and return a failed dict."""
		from src.tasks import podcast_generation as pg

		with patch.object(
			pg, "upload_to_s3_task", side_effect=ConnectionError("down")
		) as up, patch.object(pg.time, "sleep") as slept:
			result = pg._upload_to_s3_with_retries("f", "k", "b", max_attempts=3)
		assert result["status"] == "failed"
		assert "down" in result["error"]
		assert up.call_count == 3
		assert slept.call_count == 2  # backoff between attempts, none after the last


# ============================================================================
# COMPOSITION TIMELINE RESOLVER (issue #313) — the timeline must always include
# the generated audio and must never come back empty.
# ============================================================================

class TestResolveCompositionTimeline:
	"""resolve_composition_timeline builds the ordered merge timeline."""

	def _mock_session(self, snippets: list) -> MagicMock:
		session = MagicMock()
		session.execute.return_value.scalars.return_value.all.return_value = snippets
		session.__enter__ = MagicMock(return_value=session)
		session.__exit__ = MagicMock(return_value=False)
		return session

	def _snippet(self, snippet_type: str, file_path: str) -> types.SimpleNamespace:
		return types.SimpleNamespace(
			id=uuid4(), snippet_type=snippet_type, file_path=file_path
		)

	def test_no_snippets_yields_main_segment_only(self) -> None:
		"""With no project snippets the timeline is exactly the generated audio."""
		from src.tasks import podcast_generation as pg

		with patch.object(pg, "SyncSessionLocal", return_value=self._mock_session([])):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		assert timeline == [{"file_path": "/tmp/gen.mp3", "segment_type": "main_content"}]

	def test_orders_intro_and_music_before_main_and_rest_after(self, tmp_path) -> None:
		"""intro/music precede main_content; outro/midroll/ad/other follow it."""
		from src.tasks import podcast_generation as pg

		paths = {}
		for name in ("intro", "music", "outro", "ad"):
			p = tmp_path / f"{name}.mp3"
			p.write_bytes(b"x")
			paths[name] = str(p)

		snippets = [
			self._snippet("outro", paths["outro"]),
			self._snippet("intro", paths["intro"]),
			self._snippet("ad", paths["ad"]),
			self._snippet("music", paths["music"]),
		]

		with patch.object(pg, "SyncSessionLocal", return_value=self._mock_session(snippets)):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		segment_types = [seg["segment_type"] for seg in timeline]
		assert segment_types == ["intro", "music", "main_content", "outro", "ad"]
		assert timeline[2]["file_path"] == "/tmp/gen.mp3"

	def test_skips_snippets_without_local_file(self, tmp_path) -> None:
		"""Snippets whose file_path is not on local disk (S3-only) are skipped."""
		from src.tasks import podcast_generation as pg

		local = tmp_path / "intro.mp3"
		local.write_bytes(b"x")
		snippets = [
			self._snippet("intro", str(local)),
			self._snippet("outro", "audio-snippets/only-in-s3.mp3"),
		]

		with patch.object(pg, "SyncSessionLocal", return_value=self._mock_session(snippets)):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		assert [seg["segment_type"] for seg in timeline] == ["intro", "main_content"]

	def test_none_project_id_yields_main_segment_only(self) -> None:
		"""No project scope → no snippet query; timeline is just the main segment."""
		from src.tasks import podcast_generation as pg

		with patch.object(pg, "SyncSessionLocal") as session_cls:
			timeline = pg.resolve_composition_timeline(None, "/tmp/gen.mp3")

		session_cls.assert_not_called()
		assert timeline == [{"file_path": "/tmp/gen.mp3", "segment_type": "main_content"}]

	def test_db_error_degrades_to_main_segment_only(self) -> None:
		"""A snippet-query failure must not fail composition: main audio still merges."""
		from src.tasks import podcast_generation as pg

		with patch.object(pg, "SyncSessionLocal", side_effect=ConnectionError("db down")):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		assert timeline == [{"file_path": "/tmp/gen.mp3", "segment_type": "main_content"}]
