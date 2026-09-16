"""
Unit tests for content extraction Celery task.

Tests cover:
- Task signature validation (parameter names)
- Task routing to correct extraction method per source_type
- Retry logic on transient errors
- No-retry on validation errors (ValueError)
- Return value structure
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery.exceptions import Retry

from src.tasks.content_extraction import extract_content_task


# ============================================================================
# SIGNATURE TESTS
# ============================================================================


def test_task_accepts_content_source_id_parameter():
	"""Task signature must accept content_source_id parameter."""
	import inspect
	sig = inspect.signature(extract_content_task.run)
	params = list(sig.parameters.keys())
	assert 'content_source_id' in params


def test_task_accepts_source_type_parameter():
	"""Task signature must accept source_type parameter."""
	import inspect
	sig = inspect.signature(extract_content_task.run)
	params = list(sig.parameters.keys())
	assert 'source_type' in params


# ============================================================================
# URL EXTRACTION ROUTING TESTS
# ============================================================================


def test_task_routes_url_to_extract_from_url():
	"""Task must call extract_from_url for source_type='url'."""
	content_source_id = str(uuid4())

	mock_result = MagicMock()
	mock_result.success = True
	mock_result.word_count = 100
	mock_result.error_message = None

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.return_value = {
			"status": "complete",
			"word_count": 100,
			"error_message": None,
		}
		with patch.object(extract_content_task, 'update_state'):
			result = extract_content_task.run(
				content_source_id=content_source_id,
				source_type='url',
			)

	assert result["status"] == "complete"
	assert result["word_count"] == 100
	assert result["error_message"] is None
	mock_run.assert_called_once()


def test_task_routes_pdf_to_extract_from_pdf():
	"""Task must call the async helper for source_type='pdf'."""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.return_value = {
			"status": "complete",
			"word_count": 250,
			"error_message": None,
		}
		with patch.object(extract_content_task, 'update_state'):
			result = extract_content_task.run(
				content_source_id=content_source_id,
				source_type='pdf',
			)

	assert result["status"] == "complete"
	assert result["word_count"] == 250


def test_task_routes_text_to_extract_from_text():
	"""Task must call the async helper for source_type='text'."""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.return_value = {
			"status": "complete",
			"word_count": 50,
			"error_message": None,
		}
		with patch.object(extract_content_task, 'update_state'):
			result = extract_content_task.run(
				content_source_id=content_source_id,
				source_type='text',
			)

	assert result["status"] == "complete"
	assert result["word_count"] == 50


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


def test_task_returns_failed_on_value_error_no_retry():
	"""Task must return failed without retry on ValueError (validation error)."""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.side_effect = ValueError("Content source not found")
		with patch.object(extract_content_task, 'update_state'):
			result = extract_content_task.run(
				content_source_id=content_source_id,
				source_type='url',
			)

	assert result["status"] == "failed"
	assert "not found" in result["error_message"].lower()
	assert result["word_count"] == 0


def test_task_retries_on_transient_error():
	"""Task must attempt retry (Celery raises Retry to suspend the task) on non-ValueError exceptions."""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.side_effect = ConnectionError("Network error")
		with patch.object(extract_content_task, 'update_state'), \
			 patch.object(extract_content_task, 'retry', side_effect=Retry("scheduled", None)) as mock_retry:
			with pytest.raises(Retry):
				extract_content_task.run(
					content_source_id=content_source_id,
					source_type='url',
				)

	mock_retry.assert_called_once()


def test_exhausted_retries_propagate_the_original_exception():
	"""With retries at the limit the task fails, so link_error fires (#520).

	Every other retry test in this file patches `retry` to raise
	MaxRetriesExceededError. Celery never raises that when retry() is given
	an `exc=` — it re-raises the original exception instead. This test uses
	Celery's own retry() (no mock) so it pins the real behaviour.
	"""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.side_effect = ConnectionError("Persistent failure")
		with patch.object(extract_content_task, 'update_state'):
			extract_content_task.push_request(
				retries=extract_content_task.max_retries,
				called_directly=False,
				id="exhaust-extract",
			)
			try:
				with pytest.raises(ConnectionError, match="Persistent failure"):
					extract_content_task.run(
						content_source_id=content_source_id,
						source_type='url',
					)
			finally:
				extract_content_task.pop_request()


# ============================================================================
# RETURN VALUE STRUCTURE TESTS
# ============================================================================


def test_task_return_value_has_required_keys():
	"""Task result must contain status, word_count, and error_message keys."""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.return_value = {
			"status": "complete",
			"word_count": 42,
			"error_message": None,
		}
		with patch.object(extract_content_task, 'update_state'):
			result = extract_content_task.run(
				content_source_id=content_source_id,
				source_type='text',
			)

	assert "status" in result
	assert "word_count" in result
	assert "error_message" in result


def test_task_failed_result_has_error_message():
	"""Failed task result must include error_message."""
	content_source_id = str(uuid4())

	with patch('src.tasks.content_extraction._extract_content_async', MagicMock()), \
		 patch('src.tasks.content_extraction.asyncio.run') as mock_run:
		mock_run.return_value = {
			"status": "failed",
			"word_count": 0,
			"error_message": "URL not found (404): https://example.com",
		}
		with patch.object(extract_content_task, 'update_state'):
			result = extract_content_task.run(
				content_source_id=content_source_id,
				source_type='url',
			)

	assert result["status"] == "failed"
	assert result["error_message"] is not None
	assert "404" in result["error_message"]
