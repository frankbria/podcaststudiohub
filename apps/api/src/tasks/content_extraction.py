"""
Celery task for content extraction from various source types.

Wraps the async ContentExtractionService methods with a synchronous Celery task
interface using asyncio.run(). Supports URL, PDF, and text source types.

Retry strategy:
- Retries up to 3 times on transient errors (network, unexpected exceptions)
- No retry on ValueError (validation errors — permanent failures)
- Exponential backoff: 60s, 120s, 240s between retries
"""

import asyncio
import logging
import uuid as uuid_module
from typing import Dict, Any

from celery import Task

from src.worker import celery_app

logger = logging.getLogger(__name__)


async def _extract_content_async(
	content_source_id: str,
	source_type: str,
) -> Dict[str, Any]:
	"""
	Async helper that runs the ContentExtractionService.

	Uses celery_async_session to create an async database session compatible
	with the service's async interface (per-call engine — the shared pool
	cannot be reused across asyncio.run() event loops).

	Args:
		content_source_id: UUID string of the content source to extract
		source_type: Type of source ('url', 'pdf', 'text')

	Returns:
		Dictionary with status, word_count, and error_message

	Raises:
		ValueError: If content source not found or type mismatch
		Exception: On extraction errors (caller handles retry)
	"""
	from src.database import celery_async_session
	from src.services.content_extraction_service import ContentExtractionService

	service = ContentExtractionService()
	content_uuid = uuid_module.UUID(content_source_id)

	async with celery_async_session() as db:
		if source_type == 'url':
			result = await service.extract_from_url(db, content_uuid)
		elif source_type == 'pdf':
			result = await service.extract_from_pdf(db, content_uuid)
		elif source_type == 'text':
			result = await service.extract_from_text(db, content_uuid)
		else:
			raise ValueError(
				f"Unsupported source type: {source_type}. Supported types: url, pdf, text"
			)

		return {
			"status": "complete" if result.success else "failed",
			"word_count": result.word_count,
			"error_message": result.error_message,
		}


async def _validate_url_reachability_async(content_source_id: str) -> Dict[str, Any]:
	"""
	Verify a URL content source is reachable, off the request path (issue #322).

	Replaces the create-time HEAD that used to block the request for up to
	~40s: on an unreachable / non-2xx / timeout / redirect-loop target the
	source is marked ``extraction_status='failed'`` with the error message; a
	reachable target is left ``pending``. Only meaningful for the
	``auto_extract=False`` case — the default extraction path already re-fetches
	the URL and reports failure itself.

	Runs under ``celery_async_session`` (the sync Celery role bypasses RLS,
	same as ``extract_content_task``).
	"""
	from src.database import celery_async_session
	from src.services.content_service import get_content_source_by_id
	from src.services.source_validator_service import (
		SourceValidatorService,
		URLValidationError,
	)

	content_uuid = uuid_module.UUID(content_source_id)
	async with celery_async_session() as db:
		content_source = await get_content_source_by_id(db, content_uuid)
		if content_source is None:
			raise ValueError(f"Content source {content_source_id} not found")
		if content_source.source_type != "url":
			return {"status": "skipped", "reason": "not a url source"}

		url = content_source.source_data.get("url")
		if not url:
			return {"status": "skipped", "reason": "missing url"}

		try:
			await SourceValidatorService()._check_url_accessibility(url)
		except URLValidationError as exc:
			content_source.extraction_status = "failed"
			content_source.error_message = str(exc)
			await db.commit()
			return {"status": "failed", "error_message": str(exc)}

		return {"status": "reachable"}


@celery_app.task(bind=True, name="validate_url_reachability", max_retries=3, time_limit=120)
def validate_url_reachability_task(
	self: Task,
	content_source_id: str,
) -> Dict[str, Any]:
	"""
	Check a URL content source's reachability via Celery (issue #322).

	Dispatched by the create endpoint when ``auto_extract`` is False so the
	network HEAD never blocks the create request. An unreachable target is a
	permanent result (the source is marked failed) — only unexpected errors
	(e.g. transient DB failures) retry.

	Returns a dict with ``status`` ('reachable', 'failed', or 'skipped') and,
	on failure, ``error_message``.
	"""
	logger.info(f"Checking URL reachability for content source {content_source_id}")
	try:
		result = asyncio.run(_validate_url_reachability_async(content_source_id))
		logger.info(
			f"Reachability check for {content_source_id}: {result['status']}"
		)
		return result

	except ValueError as e:
		# Missing source — permanent, do not retry.
		logger.error(f"Reachability check error for {content_source_id}: {str(e)}")
		return {"status": "failed", "error_message": str(e)}

	except Exception as e:
		logger.error(f"Reachability check error for {content_source_id}: {str(e)}")
		retry_countdown = 60 * (2 ** self.request.retries)
		try:
			raise self.retry(exc=e, countdown=retry_countdown)
		except self.MaxRetriesExceededError:
			return {
				"status": "failed",
				"error_message": f"Max retries exceeded: {str(e)}",
			}


@celery_app.task(bind=True, name="extract_content", max_retries=3, time_limit=120)
def extract_content_task(
	self: Task,
	content_source_id: str,
	source_type: str,
) -> Dict[str, Any]:
	"""
	Extract content from a content source via Celery.

	Dispatches to the appropriate ContentExtractionService method based on
	source_type. Updates ContentSource.extraction_status and
	ContentSource.extracted_content in the database via the service.

	Args:
		self: Celery task instance (for retry and state updates)
		content_source_id: UUID string of content source to extract
		source_type: Type of source ('url', 'pdf', 'text')

	Returns:
		Dictionary with:
		- status: 'complete' or 'failed'
		- word_count: Number of words extracted (0 if failed)
		- error_message: Error details (None if succeeded)
	"""
	logger.info(
		f"Starting content extraction for source {content_source_id} "
		f"(type: {source_type})"
	)

	try:
		result = asyncio.run(_extract_content_async(content_source_id, source_type))
		logger.info(
			f"Extraction completed for {content_source_id}: {result['status']}"
		)
		return result

	except ValueError as e:
		# Validation errors are permanent — do not retry
		logger.error(f"Validation error for {content_source_id}: {str(e)}")
		return {
			"status": "failed",
			"word_count": 0,
			"error_message": str(e),
		}

	except Exception as e:
		logger.error(f"Error extracting content for {content_source_id}: {str(e)}")
		retry_countdown = 60 * (2 ** self.request.retries)
		try:
			raise self.retry(exc=e, countdown=retry_countdown)
		except self.MaxRetriesExceededError:
			return {
				"status": "failed",
				"word_count": 0,
				"error_message": f"Max retries exceeded: {str(e)}",
			}
