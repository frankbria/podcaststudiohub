"""
RSS Feed router for podcast feed management endpoints.

Provides endpoints for generating, retrieving, and updating RSS 2.0 podcast
feeds. The public feed endpoint requires no authentication, while management
endpoints require a valid JWT token.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.rss_feed import RSSFeedResponse, RSSFeedUpdate
from ..services.rss_generation_service import RSSGenerationService, rss_feed_s3_key
from ..services.project_service import get_project_by_id
from ..tasks.podcast_generation import build_podcast_s3_key

logger = logging.getLogger(__name__)

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
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=str(e),
		)
	except Exception:
		logger.exception("Failed to generate RSS feed for project %s", project_id)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to generate RSS feed.",
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
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=str(e),
		)
	except Exception:
		logger.exception("Failed to regenerate RSS feed for project %s", project_id)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to regenerate RSS feed.",
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
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Serve public RSS feed XML for a project.

	No authentication required. Returns the RSS 2.0 feed XML with
	appropriate Content-Type and caching headers.

	Deliberately no database read: an unauthenticated request carries no
	tenant context, so FORCE RLS on rss_feeds would return zero rows and
	404 every real platform fetch (#385). The S3 key is deterministic, so
	the object's existence is the "feed was generated" check.

	Args:
		project_id: UUID of the project
		rss_service: RSS generation service (for S3 access)

	Returns:
		RSS 2.0 XML response with Content-Type: application/rss+xml

	Raises:
		HTTPException 404: If the feed has not been generated
	"""
	s3_key = rss_feed_s3_key(project_id)

	try:
		xml_content = await _fetch_rss_from_s3(rss_service, s3_key)
	except FileNotFoundError:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Podcast feed not found",
		)
	except Exception:
		logger.exception("Failed to fetch RSS feed for project %s", project_id)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to fetch RSS feed.",
		)

	return Response(
		content=xml_content,
		media_type="application/rss+xml; charset=utf-8",
		headers={
			"Cache-Control": "max-age=3600, public",
			"ETag": f'"{hash(xml_content)}"',
		},
	)


# methods= is explicit because FastAPI does not add HEAD to GET routes, and
# podcast platforms HEAD enclosure URLs before downloading (405 breaks ingestion)
@public_router.api_route(
	"/feeds/episodes/{user_id}/{episode_id}/audio.mp3", methods=["GET", "HEAD"]
)
async def get_public_episode_audio(
	user_id: UUID,
	episode_id: UUID,
	rss_service: RSSGenerationService = Depends(get_rss_service),
):
	"""
	Redirect to a fresh presigned S3 URL for an episode's audio (#391).

	Public, unauthenticated: this is the URL podcast platforms get in the
	feed's <enclosure> and hit to download audio. The bucket is private, so
	the enclosure cannot point at S3 directly; presigned URLs alone expire
	(7-day max) while RSS feeds are long-lived. A per-request 302 to a
	short-lived presigned URL solves both, and S3 serves Range requests on
	the redirect target natively.

	Deliberately no database read: episodes is FORCE RLS and an
	unauthenticated request has no tenant context (#385). The S3 key is
	derived from the URL via the canonical key layout (#215), so the
	object's existence is the access check — the path is an unguessable
	UUID-pair URL, exactly like the feed endpoint.
	"""
	s3_key = build_podcast_s3_key(str(user_id), str(episode_id))

	try:
		if not await rss_service.storage.file_exists(s3_key):
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Episode audio not found",
			)
		presigned_url = await rss_service.storage.generate_presigned_url(
			s3_key, expiration=3600
		)
	except HTTPException:
		raise
	except Exception:
		logger.exception("Failed to presign audio for episode %s", episode_id)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to fetch episode audio.",
		)

	return RedirectResponse(
		presigned_url,
		status_code=status.HTTP_302_FOUND,
		# The Location is minted per request and short-lived — never cache it
		headers={"Cache-Control": "no-store"},
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
