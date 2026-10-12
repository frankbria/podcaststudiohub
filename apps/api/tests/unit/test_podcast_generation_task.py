"""
Tests for podcast generation Celery task parameter handling.

The task hands its inputs to the in-repo engine through ``_run_native_engine``
(#543). That boundary is faked with an ``autospec`` of the real function, so a
call with a kwarg the engine does not accept fails the test — the failure mode
issue #204 was about with the previous engine.

YouTube URLs arrive via ``urls``; file/PDF sources arrive pre-extracted via
``text_content``.
"""

import inspect
import os
import shutil
import tempfile
import types
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import uuid4

import pytest

from src.tasks.podcast_generation import _run_native_engine, generate_podcast_task
from src.tasks.s3_upload import GENERATION_RUN_DIR_PREFIX


def _fake_engine(
	audio_path: str = "/tmp/output.mp3",
	transcript_path: str | None = None,
	side_effect: Any = None,
) -> MagicMock:
	"""Autospec of the real engine boundary: rejects any call it would reject."""
	return create_autospec(
		_run_native_engine,
		return_value=(audio_path, transcript_path),
		side_effect=side_effect,
	)


def _run_task(engine: MagicMock | None = None, **task_kwargs: Any) -> tuple[dict[str, Any], MagicMock]:
	"""Run the Celery task body with the engine faked, return (result, mock_engine)."""
	mock_engine = engine or _fake_engine()

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=60000)

	try:
		with patch.object(generate_podcast_task, 'update_state'), \
			 patch('src.tasks.podcast_generation._run_native_engine', mock_engine), \
			 patch('src.tasks.podcast_generation.os.path.getsize', return_value=1024), \
			 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
			 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

			mock_audio.from_file.return_value = audio_instance
			result = generate_podcast_task.run(**task_kwargs)
	finally:
		# Finalize (patched out here) owns run-dir cleanup on success.
		if mock_engine.call_args is not None:
			shutil.rmtree(mock_engine.call_args.args[2], ignore_errors=True)

	return result, mock_engine


# ============================================================================
# PARAMETER NAME TESTS (signature inspection)
# ============================================================================

def test_task_does_not_accept_invalid_parameters():
	"""Task must not expose file_paths / youtube_urls."""
	sig = inspect.signature(generate_podcast_task.run)
	params = list(sig.parameters.keys())
	assert 'file_paths' not in params, (
		"Task must not accept 'file_paths' — file sources are pre-extracted into "
		"text_content."
	)
	assert 'youtube_urls' not in params, (
		"Task must not accept 'youtube_urls' — YouTube URLs flow through 'urls'."
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
# INTEGRATION: task passes parameters correctly to the engine
# ============================================================================

def test_task_passes_text_content_to_engine():
	"""Task must hand text_content to the engine."""
	text_content = "This is the podcast content."
	_, mock_engine = _run_task(episode_id=str(uuid4()), text_content=text_content)

	mock_engine.assert_called_once()
	call_kwargs = mock_engine.call_args.kwargs
	assert call_kwargs.get('text_content') == text_content, (
		f"Expected text_content={text_content!r}, got {call_kwargs.get('text_content')!r}"
	)


def test_task_passes_urls_to_engine():
	"""URLs (including YouTube) must be forwarded via the 'urls' kwarg."""
	urls = ["https://youtube.com/watch?v=abc", "https://example.com"]
	_, mock_engine = _run_task(episode_id=str(uuid4()), urls=urls)

	call_kwargs = mock_engine.call_args.kwargs
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
	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=120000)
	mock_engine = _fake_engine("/tmp/episode.mp3")

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch('src.tasks.podcast_generation._run_native_engine', mock_engine), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=2048), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance

		result = generate_podcast_task.run(
			episode_id=str(uuid4()),
			urls=["https://example.com"],
		)
	shutil.rmtree(mock_engine.call_args.args[2], ignore_errors=True)

	assert result["status"] == "success"
	assert result["audio_file_path"] == "/tmp/episode.mp3"
	assert result["file_size_bytes"] == 2048
	assert result["error"] is None


def test_exhausted_retries_propagate_the_original_exception():
	"""With retries at the limit and NO retry mock, real Celery decides: the
	task fails with the engine's own exception rather than returning (#520)."""
	mock_engine = _fake_engine(side_effect=RuntimeError("Engine crashed"))

	generate_podcast_task.push_request(
		retries=generate_podcast_task.max_retries,
		called_directly=False,
		id="exhausted-gen",
	)
	try:
		with patch.object(generate_podcast_task, 'update_state'), \
			 patch('src.tasks.podcast_generation._run_native_engine', mock_engine):
			with pytest.raises(RuntimeError, match="Engine crashed"):
				generate_podcast_task.run(
					episode_id=str(uuid4()),
					urls=["https://example.com"],
				)
	finally:
		generate_podcast_task.pop_request()


# ============================================================================
# ISSUE #309 — transcript_path must not be fabricated; engine output must be
# routed into a per-run temp dir so post-upload cleanup can remove it.
# ============================================================================

def test_success_result_transcript_path_is_the_engines():
	"""The result carries the transcript path the engine returned — never a
	string-substituted path to a file that does not exist (issue #309)."""
	result, _ = _run_task(episode_id=str(uuid4()), urls=["https://example.com"])
	assert result["status"] == "success"
	assert result["transcript_path"] is None

	stored = "podcasts/user-u/episode-e_transcript.json"
	result, _ = _run_task(
		_fake_engine("/tmp/output.mp3", stored),
		episode_id=str(uuid4()), urls=["https://example.com"],
	)
	assert result["transcript_path"] == stored


def test_task_routes_engine_output_to_per_run_temp_dir():
	"""The engine writes into a per-run directory under the system temp root,
	named with the cleanup-recognized prefix, that exists before it runs."""
	seen = {}

	def record(task, episode_id, run_dir, **kwargs):
		seen["run_dir"] = run_dir
		seen["existed"] = os.path.isdir(run_dir)
		return "/tmp/output.mp3", None

	_run_task(
		_fake_engine(side_effect=record),
		episode_id=str(uuid4()), urls=["https://example.com"],
	)

	run_dir = os.path.realpath(seen["run_dir"])
	temp_root = os.path.realpath(tempfile.gettempdir())
	assert os.path.commonpath([temp_root, run_dir]) == temp_root
	assert os.path.basename(run_dir).startswith(GENERATION_RUN_DIR_PREFIX)
	assert seen["existed"], "run dir must exist before the engine writes to it"


def test_terminal_failure_cleans_up_run_dir():
	"""When generation fails terminally, the attempt's run dir must be removed
	so failed attempts don't leak temp artifacts either."""
	run_dir = tempfile.mkdtemp(prefix=GENERATION_RUN_DIR_PREFIX)
	try:
		mock_engine = _fake_engine(side_effect=RuntimeError("boom"))
		generate_podcast_task.push_request(
			retries=generate_podcast_task.max_retries,
			called_directly=False,
			id="exhausted-run-dir",
		)
		try:
			with patch.object(generate_podcast_task, 'update_state'), \
				 patch('src.tasks.podcast_generation._run_native_engine', mock_engine), \
				 patch('src.tasks.podcast_generation.tempfile.mkdtemp', return_value=run_dir):
				with pytest.raises(RuntimeError, match="boom"):
					generate_podcast_task.run(
						episode_id=str(uuid4()),
						urls=["https://example.com"],
					)
		finally:
			generate_podcast_task.pop_request()
		assert not os.path.exists(run_dir)
	finally:
		shutil.rmtree(run_dir, ignore_errors=True)


def test_soft_timeout_cleans_up_run_dir():
	"""SoftTimeLimitExceeded is a separate terminal branch (it bypasses the
	generic except) — it must also remove the attempt's run dir."""
	from celery.exceptions import SoftTimeLimitExceeded

	run_dir = tempfile.mkdtemp(prefix=GENERATION_RUN_DIR_PREFIX)
	try:
		mock_engine = _fake_engine(side_effect=SoftTimeLimitExceeded())
		with patch.object(generate_podcast_task, 'update_state'), \
			 patch('src.tasks.podcast_generation._run_native_engine', mock_engine), \
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

	def _snippet(
		self, snippet_type: str, file_path: str, s3_key: str = None
	) -> types.SimpleNamespace:
		return types.SimpleNamespace(
			id=uuid4(), snippet_type=snippet_type, file_path=file_path, s3_key=s3_key
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

	def test_skips_snippets_without_local_file_or_s3_key(self, tmp_path) -> None:
		"""Snippets with no local file and no S3 object are skipped."""
		from src.tasks import podcast_generation as pg

		local = tmp_path / "intro.mp3"
		local.write_bytes(b"x")
		snippets = [
			self._snippet("intro", str(local)),
			self._snippet("outro", "audio-snippets/gone.mp3", s3_key=None),
		]

		with patch.object(pg, "SyncSessionLocal", return_value=self._mock_session(snippets)):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		assert [seg["segment_type"] for seg in timeline] == ["intro", "main_content"]

	def test_s3_backed_snippets_included_as_s3_entries(self) -> None:
		"""Production shape (#376): file_path holds the S3 key, s3_key is set, and
		S3 is configured — snippets are included as s3_key entries for the merge
		task to download, ordered around the main segment."""
		from src.tasks import podcast_generation as pg

		snippets = [
			self._snippet("outro", "audio-snippets/u1/s2.mp3", s3_key="audio-snippets/u1/s2.mp3"),
			self._snippet("intro", "audio-snippets/u1/s1.mp3", s3_key="audio-snippets/u1/s1.mp3"),
		]

		with patch.object(pg, "SyncSessionLocal", return_value=self._mock_session(snippets)), \
			 patch.object(pg.settings, "AWS_S3_BUCKET", "test-bucket"):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		assert timeline == [
			{"s3_key": "audio-snippets/u1/s1.mp3", "segment_type": "intro"},
			{"file_path": "/tmp/gen.mp3", "segment_type": "main_content"},
			{"s3_key": "audio-snippets/u1/s2.mp3", "segment_type": "outro"},
		]

	def test_s3_backed_snippets_skipped_when_s3_not_configured(self) -> None:
		"""Without AWS_S3_BUCKET the merge task cannot download, so s3_key-only
		snippets stay skipped and the timeline degrades to main-only."""
		from src.tasks import podcast_generation as pg

		snippets = [
			self._snippet("intro", "audio-snippets/u1/s1.mp3", s3_key="audio-snippets/u1/s1.mp3"),
		]

		with patch.object(pg, "SyncSessionLocal", return_value=self._mock_session(snippets)), \
			 patch.object(pg.settings, "AWS_S3_BUCKET", None):
			timeline = pg.resolve_composition_timeline(uuid4(), "/tmp/gen.mp3")

		assert timeline == [{"file_path": "/tmp/gen.mp3", "segment_type": "main_content"}]

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
