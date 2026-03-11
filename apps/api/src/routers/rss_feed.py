"""
RSS Feed router for podcast feed management endpoints.

Provides endpoints for generating, retrieving, and updating RSS 2.0 podcast
feeds. The public feed endpoint requires no authentication, while management
endpoints require a valid JWT token.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.rss_feed import (
	RSSFeedResponse,
	RSSFeedUpdate,
	RSSValidationStatusResponse,
	RSSValidationTriggerResponse,
)
from ..services.rss_generation_service import RSSGenerationService
from ..services.project_service import get_project_by_id
from ..tasks.rss_generation import generate_rss_feed_task

# Authenticated management endpoints nested under /projects
router = APIRouter(tags=["rss-feed"])

# Public feed endpoint (no auth required)
public_router = APIRouter(tags=["rss-feed"])


def get_rss_service() -> RSSGenerationService:
	"""Dependency: return a shared RSSGenerationService instance."""
	return RSSGenerationService()


# ============================================================================
# MANAGEMENT ENDPOINTS (authenticated, under /projects)
# ============================================================================

@router.post(
	"/projects/{project_id}/rss-feed/generate",
	response_model=RSSFeedResponse,
	status_code=status.HTTP_200_OK,
)
async def generate_rss_feed(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Generate RSS 2.0 feed for all completed episodes in a project.

	Retrieves all completed episodes, builds RSS XML document,
	uploads to S3 with public access, and stores the public URL in
	the RSSFeed record.

	Args:
		project_id: UUID of the project to generate feed for
		current_user: Authenticated user (from JWT token)
		db: Database session
		rss_service: RSS generation service

	Returns:
		RSSFeed object with s3_key, public_url, and last_generated

	Raises:
		HTTPException 404: If project not found
		HTTPException 422: If podcast_metadata missing required fields
		HTTPException 500: If S3 upload fails
	"""
	# Verify project exists (RLS ensures tenant isolation)
	project = await get_project_by_id(db, project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Project {project_id} not found",
		)

	try:
		rss_feed = await rss_service.generate_rss_for_project(
			db=db,
			project_id=project_id,
			user_id=current_user.id,
		)
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=str(e),
		)
	except Exception as e:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to generate RSS feed: {str(e)}",
		)

	return rss_feed


@router.get(
	"/projects/{project_id}/rss-feed",
	response_model=RSSFeedResponse,
)
async def get_rss_feed(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Get RSS feed metadata for a project.

	Returns the RSSFeed record with s3_key, public_url, last_generated,
	and validation_status.

	Args:
		project_id: UUID of the project
		current_user: Authenticated user (from JWT token)
		db: Database session
		rss_service: RSS generation service

	Returns:
		RSSFeed object

	Raises:
		HTTPException 404: If project not found or feed not yet generated
	"""
	# Verify project exists (RLS ensures tenant isolation)
	project = await get_project_by_id(db, project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Project {project_id} not found",
		)

	rss_feed = await rss_service.get_rss_feed(db, project_id)
	if rss_feed is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"RSS feed not generated yet. Call POST /projects/{project_id}/rss-feed/generate",
		)

	return rss_feed


@router.put(
	"/projects/{project_id}/rss-feed",
	response_model=RSSFeedResponse,
)
async def update_rss_feed(
	project_id: UUID,
	update_data: RSSFeedUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Update podcast metadata and regenerate RSS feed.

	Merges the provided podcast_metadata fields into the project's existing
	podcast_metadata, then triggers feed regeneration.

	Args:
		project_id: UUID of the project
		update_data: Metadata fields to update (triggers regeneration)
		current_user: Authenticated user (from JWT token)
		db: Database session
		rss_service: RSS generation service

	Returns:
		Updated RSSFeed object with regenerated feed

	Raises:
		HTTPException 404: If project not found
		HTTPException 422: If updated metadata missing required fields
	"""
	# Verify project exists (RLS ensures tenant isolation)
	project = await get_project_by_id(db, project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Project {project_id} not found",
		)

	# Merge updated metadata into existing project metadata
	new_metadata = update_data.podcast_metadata.model_dump(exclude_unset=True)
	merged_metadata = {**(project.podcast_metadata or {}), **new_metadata}
	project.podcast_metadata = merged_metadata
	await db.commit()

	# Regenerate RSS feed with updated metadata
	try:
		rss_feed = await rss_service.generate_rss_for_project(
			db=db,
			project_id=project_id,
			user_id=current_user.id,
		)
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=str(e),
		)
	except Exception as e:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to regenerate RSS feed: {str(e)}",
		)

	return rss_feed


# ============================================================================
# PUBLIC FEED ENDPOINT (no authentication required)
# ============================================================================

@public_router.get(
	"/feeds/{project_id}/podcast.xml",
	response_class=Response,
)
async def get_public_rss_feed(
	project_id: UUID,
	db: AsyncSession = Depends(get_db),
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Serve public RSS feed XML for a project.

	No authentication required. Returns the RSS 2.0 feed XML with
	appropriate Content-Type and caching headers.

	Fetches feed XML from S3 if available, otherwise returns 404.

	Args:
		project_id: UUID of the project
		db: Database session
		rss_service: RSS generation service

	Returns:
		RSS 2.0 XML response with Content-Type: application/rss+xml

	Raises:
		HTTPException 404: If project or feed not found
	"""
	rss_feed = await rss_service.get_rss_feed(db, project_id)
	if rss_feed is None or not rss_feed.public_url:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Podcast feed not found",
		)

	# Fetch XML from S3
	try:
		xml_content = await _fetch_rss_from_s3(rss_service, rss_feed.s3_key)
	except Exception as e:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to fetch RSS feed: {str(e)}",
		)

	return Response(
		content=xml_content,
		media_type="application/rss+xml; charset=utf-8",
		headers={
			"Cache-Control": "max-age=3600, public",
			"ETag": f'"{hash(xml_content)}"',
		},
	)


@router.post(
	"/projects/{project_id}/rss-feed/validate",
	response_model=RSSValidationTriggerResponse,
	status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_rss_validation(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Trigger RSS feed regeneration and validation as a background task.

	Dispatches a Celery task to regenerate the feed, validate it against
	Apple Podcasts, Spotify, and Google Podcasts, then upload to S3.

	Args:
		project_id: UUID of the project
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		202 Accepted with task_id for polling status

	Raises:
		HTTPException 404: If project not found
	"""
	project = await get_project_by_id(db, project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Project {project_id} not found",
		)

	task = generate_rss_feed_task.delay(str(project_id), str(current_user.tenant_id))

	return RSSValidationTriggerResponse(
		task_id=task.id,
		status="queued",
		message="RSS feed generation and validation has been queued",
	)


@router.get(
	"/projects/{project_id}/rss-feed/validation-status",
	response_model=RSSValidationStatusResponse,
)
async def get_rss_validation_status(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Get the most recent RSS feed validation results.

	Returns the stored validation status from the last time the feed
	was generated and validated.

	Args:
		project_id: UUID of the project
		current_user: Authenticated user (from JWT token)
		db: Database session
		rss_service: RSS generation service

	Returns:
		Validation results for Apple Podcasts, Spotify, and Google Podcasts

	Raises:
		HTTPException 404: If project or RSS feed not found
	"""
	project = await get_project_by_id(db, project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Project {project_id} not found",
		)

	rss_feed = await rss_service.get_rss_feed(db, project_id)
	if rss_feed is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"RSS feed not generated yet for project {project_id}",
		)

	validation_status = rss_feed.validation_status or {}
	return RSSValidationStatusResponse(
		last_validated_at=validation_status.get("last_validated_at"),
		apple_podcasts=validation_status.get("apple_podcasts"),
		spotify=validation_status.get("spotify"),
		google_podcasts=validation_status.get("google_podcasts"),
	)


async def _fetch_rss_from_s3(rss_service: RSSGenerationService, s3_key: str) -> bytes:
	"""
	Download RSS XML from S3 and return as bytes.

	Args:
		rss_service: RSS generation service (for storage access)
		s3_key: S3 object key

	Returns:
		RSS XML content as bytes
	"""
	import tempfile
	import os

	with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
		tmp_path = tmp.name

	try:
		await rss_service.storage.download_file(s3_key, tmp_path)
		with open(tmp_path, "rb") as f:
			return f.read()
	finally:
		if os.path.exists(tmp_path):
			os.unlink(tmp_path)
