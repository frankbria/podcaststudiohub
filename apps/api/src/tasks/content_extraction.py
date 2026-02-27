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

	Uses AsyncSessionLocal to create an async database session compatible
	with the service's async interface.

	Args:
		content_source_id: UUID string of the content source to extract
		source_type: Type of source ('url', 'pdf', 'text')

	Returns:
		Dictionary with status, word_count, and error_message

	Raises:
		ValueError: If content source not found or type mismatch
		Exception: On extraction errors (caller handles retry)
	"""
	from src.database import AsyncSessionLocal
	from src.services.content_extraction_service import ContentExtractionService

	service = ContentExtractionService()
	content_uuid = uuid_module.UUID(content_source_id)

	async with AsyncSessionLocal() as db:
		if source_type == 'url':
			result = await service.extract_from_url(db, content_uuid)
		elif source_type == 'pdf':
			result = await service.extract_from_pdf(db, content_uuid)
		elif source_type == 'text':
			result = await service.extract_from_text(db, content_uuid)
		else:
			raise ValueError(f"Unsupported source type: {source_type}")

		return {
			"status": "complete" if result.success else "failed",
			"word_count": result.word_count,
			"error_message": result.error_message,
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
