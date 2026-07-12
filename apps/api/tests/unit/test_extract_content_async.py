"""
Unit tests for _extract_content_async helper in content_extraction task.

The existing test_content_extraction_task.py tests the Celery task surface by
mocking asyncio.run, so _extract_content_async (lines 46-62) is never called.
These tests call _extract_content_async directly with a mocked celery_async_session
and mocked ContentExtractionService to cover those lines.

Tests cover:
- url source_type routes to extract_from_url
- pdf source_type routes to extract_from_pdf
- text source_type routes to extract_from_text
- unsupported source_type raises ValueError
- result shape when service returns success
- result shape when service returns failure
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ===========================================================================
# Helpers
# ===========================================================================


def _make_service_result(success: bool, word_count: int = 0, error: str = None):
	result = MagicMock()
	result.success = success
	result.word_count = word_count
	result.error_message = error
	return result


def _make_async_context_manager(db_mock):
	"""Return an async context manager that yields db_mock."""
	cm = AsyncMock()
	cm.__aenter__ = AsyncMock(return_value=db_mock)
	cm.__aexit__ = AsyncMock(return_value=False)
	return cm


# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_extract_async_url_calls_extract_from_url():
	"""source_type='url' delegates to ContentExtractionService.extract_from_url."""
	from src.tasks.content_extraction import _extract_content_async

	mock_db = AsyncMock()
	service_result = _make_service_result(success=True, word_count=150)

	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_extraction_service.ContentExtractionService") as MockSvc:
		mock_instance = AsyncMock()
		mock_instance.extract_from_url.return_value = service_result
		MockSvc.return_value = mock_instance

		result = await _extract_content_async(str(uuid4()), "url")

	assert result["status"] == "complete"
	assert result["word_count"] == 150
	assert result["error_message"] is None


@pytest.mark.asyncio
async def test_extract_async_pdf_calls_extract_from_pdf():
	"""source_type='pdf' delegates to extract_from_pdf."""
	from src.tasks.content_extraction import _extract_content_async

	mock_db = AsyncMock()
	service_result = _make_service_result(success=True, word_count=300)

	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_extraction_service.ContentExtractionService") as MockSvc:
		mock_instance = AsyncMock()
		mock_instance.extract_from_pdf.return_value = service_result
		MockSvc.return_value = mock_instance

		result = await _extract_content_async(str(uuid4()), "pdf")

	assert result["status"] == "complete"
	assert result["word_count"] == 300


@pytest.mark.asyncio
async def test_extract_async_text_calls_extract_from_text():
	"""source_type='text' delegates to extract_from_text."""
	from src.tasks.content_extraction import _extract_content_async

	mock_db = AsyncMock()
	service_result = _make_service_result(success=False, word_count=0, error="Too short")

	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_extraction_service.ContentExtractionService") as MockSvc:
		mock_instance = AsyncMock()
		mock_instance.extract_from_text.return_value = service_result
		MockSvc.return_value = mock_instance

		result = await _extract_content_async(str(uuid4()), "text")

	assert result["status"] == "failed"
	assert result["error_message"] == "Too short"


@pytest.mark.asyncio
async def test_extract_async_unsupported_type_raises_value_error():
	"""Unsupported source_type raises ValueError."""
	from src.tasks.content_extraction import _extract_content_async

	mock_db = AsyncMock()

	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_extraction_service.ContentExtractionService"):
		with pytest.raises(ValueError, match="Unsupported source type"):
			await _extract_content_async(str(uuid4()), "video")
