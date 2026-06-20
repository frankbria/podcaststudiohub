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
import sys
import types
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import uuid4

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
		 patch.dict(sys.modules, mock_modules), \
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
		 patch.dict(sys.modules, mock_modules), \
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
		 patch.dict(sys.modules, mock_modules), \
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


class TestBuildPodcastS3Key:
	"""Canonical S3 key helper (issue #215)."""

	def test_format(self):
		from src.tasks.podcast_generation import build_podcast_s3_key

		user_id = "abc-123"
		episode_id = "ep-456"
		assert (
			build_podcast_s3_key(user_id, episode_id)
			== "podcasts/user-abc-123/episode-ep-456.mp3"
		)

	def test_uuid_inputs(self):
		from src.tasks.podcast_generation import build_podcast_s3_key

		user_id = str(uuid4())
		episode_id = str(uuid4())
		key = build_podcast_s3_key(user_id, episode_id)
		assert key == f"podcasts/user-{user_id}/episode-{episode_id}.mp3"
		assert key.startswith("podcasts/user-")
		assert key.endswith(".mp3")
