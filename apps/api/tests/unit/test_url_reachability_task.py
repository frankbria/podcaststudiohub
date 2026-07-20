"""
Unit tests for the URL reachability Celery task (issue #322).

Reachability moved off the create request path; these cover the async helper
(_validate_url_reachability_async) and the task surface
(validate_url_reachability_task) with celery_async_session, the content lookup,
and the network HEAD all mocked — mirroring test_extract_content_async.py.
"""

import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.source_validator_service import URLValidationError


def _make_async_context_manager(db_mock):
	cm = AsyncMock()
	cm.__aenter__ = AsyncMock(return_value=db_mock)
	cm.__aexit__ = AsyncMock(return_value=False)
	return cm


def _url_source(url="https://example.com/a"):
	src = MagicMock()
	src.source_type = "url"
	src.source_data = {"url": url}
	src.extraction_status = "pending"
	src.error_message = None
	return src


@pytest.mark.asyncio
async def test_reachable_url_leaves_status_pending():
	"""A reachable URL returns 'reachable' and does not touch status/commit."""
	from src.tasks.content_extraction import _validate_url_reachability_async

	mock_db = AsyncMock()
	source = _url_source()
	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_service.get_content_source_by_id", AsyncMock(return_value=source)), \
	     patch("src.services.source_validator_service.SourceValidatorService._check_url_accessibility", AsyncMock()):
		result = await _validate_url_reachability_async(str(uuid4()))

	assert result["status"] == "reachable"
	assert source.extraction_status == "pending"
	mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_unreachable_url_marks_failed_and_commits():
	"""An unreachable URL is marked extraction_status='failed' with the error."""
	from src.tasks.content_extraction import _validate_url_reachability_async

	mock_db = AsyncMock()
	source = _url_source()
	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_service.get_content_source_by_id", AsyncMock(return_value=source)), \
	     patch(
	         "src.services.source_validator_service.SourceValidatorService._check_url_accessibility",
	         AsyncMock(side_effect=URLValidationError("URL returned HTTP 404.")),
	     ):
		result = await _validate_url_reachability_async(str(uuid4()))

	assert result["status"] == "failed"
	assert "404" in result["error_message"]
	assert source.extraction_status == "failed"
	assert source.error_message == "URL returned HTTP 404."
	mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_source_raises_value_error():
	"""A missing content source raises ValueError (permanent — no retry)."""
	from src.tasks.content_extraction import _validate_url_reachability_async

	mock_db = AsyncMock()
	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_service.get_content_source_by_id", AsyncMock(return_value=None)):
		with pytest.raises(ValueError, match="not found"):
			await _validate_url_reachability_async(str(uuid4()))


@pytest.mark.asyncio
async def test_non_url_source_is_skipped():
	"""A non-URL source is a no-op (defensive — only URL sources are dispatched)."""
	from src.tasks.content_extraction import _validate_url_reachability_async

	mock_db = AsyncMock()
	source = _url_source()
	source.source_type = "text"
	with patch("src.database.celery_async_session", return_value=_make_async_context_manager(mock_db)), \
	     patch("src.services.content_service.get_content_source_by_id", AsyncMock(return_value=source)):
		result = await _validate_url_reachability_async(str(uuid4()))

	assert result["status"] == "skipped"


def test_task_signature_accepts_content_source_id():
	from src.tasks.content_extraction import validate_url_reachability_task
	assert "content_source_id" in inspect.signature(validate_url_reachability_task.run).parameters


def test_task_returns_failed_on_value_error_no_retry():
	"""ValueError (missing source) is permanent — return failed, do not retry."""
	from src.tasks.content_extraction import validate_url_reachability_task

	with patch("src.tasks.content_extraction._validate_url_reachability_async", MagicMock()), \
	     patch("src.tasks.content_extraction.asyncio.run", MagicMock(side_effect=ValueError("Content source x not found"))):
		with patch.object(validate_url_reachability_task, "update_state"):
			result = validate_url_reachability_task.run(content_source_id=str(uuid4()))

	assert result["status"] == "failed"
	assert "not found" in result["error_message"].lower()


def test_task_retries_on_transient_error():
	"""A transient (non-ValueError) error attempts retry."""
	from src.tasks.content_extraction import validate_url_reachability_task

	with patch("src.tasks.content_extraction._validate_url_reachability_async", MagicMock()), \
	     patch("src.tasks.content_extraction.asyncio.run", MagicMock(side_effect=ConnectionError("boom"))):
		with patch.object(validate_url_reachability_task, "update_state"), \
		     patch.object(
		         validate_url_reachability_task,
		         "retry",
		         side_effect=validate_url_reachability_task.MaxRetriesExceededError(),
		     ) as mock_retry:
			result = validate_url_reachability_task.run(content_source_id=str(uuid4()))

	assert result["status"] == "failed"
	mock_retry.assert_called_once()
