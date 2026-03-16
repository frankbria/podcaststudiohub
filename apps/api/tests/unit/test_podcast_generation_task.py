"""
Tests for podcast generation Celery task parameter handling.

Covers GAP-001: parameter name mismatch between router and task.
- Router calls generate_podcast_task.delay(file_paths=..., text_content=...)
- Task must accept file_paths and text_content (not pdf_paths and text)
"""

import sys
import types
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.tasks.podcast_generation import generate_podcast_task


def _mock_podcastfy_modules():
	"""Return mocked podcastfy client + modules dict for sys.modules patching."""
	mock_client = MagicMock()
	mock_podcastfy = types.ModuleType("podcastfy")
	mock_podcastfy.client = mock_client
	return mock_client, {
		"podcastfy": mock_podcastfy,
		"podcastfy.client": mock_client,
	}


# ============================================================================
# PARAMETER NAME TESTS (signature inspection — no imports needed)
# ============================================================================

def test_task_accepts_file_paths_parameter():
	"""Task signature must accept file_paths (not pdf_paths) to match router call."""
	import inspect
	sig = inspect.signature(generate_podcast_task.run)
	params = list(sig.parameters.keys())
	assert 'file_paths' in params, (
		"Task must accept 'file_paths' parameter (router sends file_paths=...)"
	)
	assert 'pdf_paths' not in params, (
		"Task must not use deprecated 'pdf_paths' parameter"
	)


def test_task_accepts_text_content_parameter():
	"""Task signature must accept text_content (not text) to match router call."""
	import inspect
	sig = inspect.signature(generate_podcast_task.run)
	params = list(sig.parameters.keys())
	assert 'text_content' in params, (
		"Task must accept 'text_content' parameter (router sends text_content=...)"
	)
	assert 'text' not in params, (
		"Task must not use deprecated 'text' parameter"
	)


def test_task_file_paths_defaults_to_none():
	"""file_paths parameter must default to None."""
	import inspect
	sig = inspect.signature(generate_podcast_task.run)
	assert sig.parameters['file_paths'].default is None


def test_task_text_content_defaults_to_none():
	"""text_content parameter must default to None."""
	import inspect
	sig = inspect.signature(generate_podcast_task.run)
	assert sig.parameters['text_content'].default is None


# ============================================================================
# INTEGRATION: task passes parameters correctly to podcastfy CLI
#
# With bind=True, `generate_podcast_task` IS the Celery task instance and
# `.run(...)` is an instance method — `self` is already bound to the task.
# We patch `update_state` on the task instance for progress calls.
# ============================================================================

def test_task_passes_file_paths_to_generate_podcast():
	"""Task must pass file_paths to generate_podcast() as the 'file' argument."""
	episode_id = str(uuid4())
	file_paths = ["/tmp/test.pdf", "/tmp/other.pdf"]

	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_gen = MagicMock(return_value="/tmp/output.mp3")
	mock_client.generate_podcast = mock_gen

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=60000)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch.dict(sys.modules, mock_modules), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=1024), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance

		generate_podcast_task.run(
			episode_id=episode_id,
			file_paths=file_paths,
		)

	mock_gen.assert_called_once()
	call_kwargs = mock_gen.call_args[1]
	assert call_kwargs.get('file') == file_paths, (
		f"Expected file={file_paths}, got file={call_kwargs.get('file')}"
	)


def test_task_passes_text_content_to_generate_podcast():
	"""Task must pass text_content to generate_podcast() as the 'text' argument."""
	episode_id = str(uuid4())
	text_content = "This is the podcast content."

	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_gen = MagicMock(return_value="/tmp/output.mp3")
	mock_client.generate_podcast = mock_gen

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=60000)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch.dict(sys.modules, mock_modules), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=1024), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance

		generate_podcast_task.run(
			episode_id=episode_id,
			text_content=text_content,
		)

	mock_gen.assert_called_once()
	call_kwargs = mock_gen.call_args[1]
	assert call_kwargs.get('text') == text_content, (
		f"Expected text={text_content!r}, got text={call_kwargs.get('text')!r}"
	)


def test_task_no_type_error_with_router_parameter_names():
	"""Calling task with router's parameter names must not raise TypeError."""
	episode_id = str(uuid4())

	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_client.generate_podcast = MagicMock(return_value="/tmp/output.mp3")

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=60000)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch.dict(sys.modules, mock_modules), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=1024), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance

		# This is exactly what the router sends — must not raise TypeError
		result = generate_podcast_task.run(
			episode_id=episode_id,
			urls=["https://example.com"],
			file_paths=["/tmp/doc.pdf"],
			text_content="Some text",
		)

	assert result["status"] == "success"


def test_task_returns_success_result():
	"""Task must return dict with status=success on successful generation."""
	episode_id = str(uuid4())

	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_client.generate_podcast = MagicMock(return_value="/tmp/episode.mp3")

	audio_instance = MagicMock()
	audio_instance.__len__ = MagicMock(return_value=120000)

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch.dict(sys.modules, mock_modules), \
		 patch('src.tasks.podcast_generation.os.path.getsize', return_value=2048), \
		 patch('src.tasks.podcast_generation.AudioSegment') as mock_audio, \
		 patch('src.tasks.podcast_generation.finalize_episode_generation_task'):

		mock_audio.from_file.return_value = audio_instance

		result = generate_podcast_task.run(
			episode_id=episode_id,
			urls=["https://example.com"],
		)

	assert result["status"] == "success"
	assert result["audio_file_path"] == "/tmp/episode.mp3"
	assert result["file_size_bytes"] == 2048
	assert result["error"] is None


def test_task_returns_failed_result_on_exception():
	"""Task must return dict with status=failed after retries exhausted."""
	episode_id = str(uuid4())

	mock_client, mock_modules = _mock_podcastfy_modules()
	mock_client.generate_podcast = MagicMock(side_effect=RuntimeError("Podcastfy crashed"))

	with patch.object(generate_podcast_task, 'update_state'), \
		 patch.dict(sys.modules, mock_modules), \
		 patch.object(
			generate_podcast_task,
			"retry",
			side_effect=generate_podcast_task.MaxRetriesExceededError(),
		 ):

		result = generate_podcast_task.run(
			episode_id=episode_id,
			urls=["https://example.com"],
		)

	assert result["status"] == "failed"
	assert "Podcastfy crashed" in result["error"]
	assert result["audio_file_path"] is None
