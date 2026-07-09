"""
Episode router for RESTful API endpoints.

Provides CRUD operations for podcast episodes with pagination, project filtering,
status filtering, and generation management. All endpoints require authentication
and automatically enforce tenant isolation via RLS.
"""

import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.episode import (
	EpisodeCreate,
	EpisodeUpdate,
	EpisodeResponse,
	EpisodeListResponse,
	BatchEpisodeCreate,
	BatchEpisodeResponse,
)
from ..services.episode_service import (
	create_episode,
	get_episodes,
	get_episode_by_id,
	update_episode,
	delete_episode,
	batch_create_episodes,
	VALID_SORT_FIELDS,
	VALID_SORT_ORDERS,
)
from ..services.storage_service import StorageService
from ..services import usage_service
from ..config import settings
from ..utils.download_utils import (
	get_episode_filename,
	parse_range_header,
	iter_s3_body,
	iter_local_file,
	is_within_dir,
)

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode_endpoint(
	episode_data: EpisodeCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Create new episode for project.

	Validates project exists and belongs to user's tenant.
	Requires authentication. Initial status is 'draft'.

	Args:
		episode_data: Episode creation data with project_id, episode_number, and episode_metadata
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created episode with all fields

	Raises:
		HTTPException: 402 if the plan's monthly episode limit is reached
		HTTPException: 404 if project not found
	"""
	# Quota gate before any write; tracking happens only after a successful create.
	if not await usage_service.check_episode_limit(db, current_user.id):
		raise HTTPException(
			status_code=status.HTTP_402_PAYMENT_REQUIRED,
			detail="Monthly episode limit reached for your plan. Please upgrade to create more episodes.",
		)

	episode = await create_episode(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		episode_data=episode_data
	)
	await usage_service.track_episode_creation(db, current_user.id, current_user.tenant_id)
	return episode


@router.get("", response_model=EpisodeListResponse)
async def list_episodes(
	project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
	status: Optional[str] = Query(None, description="Filter by generation status"),
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	search: Optional[str] = Query(None, description="Search in episode title and description (case-insensitive)"),
	date_from: Optional[datetime] = Query(None, description="Filter episodes created on or after this date (ISO 8601)"),
	date_to: Optional[datetime] = Query(None, description="Filter episodes created on or before this date (ISO 8601)"),
	tags: Optional[str] = Query(None, description="Comma-separated tags to filter by (AND logic)"),
	tts_config_id: Optional[UUID] = Query(None, description="Filter by TTS configuration ID"),
	min_duration: Optional[float] = Query(None, ge=0, description="Minimum duration in seconds"),
	max_duration: Optional[float] = Query(None, ge=0, description="Maximum duration in seconds"),
	sort_by: str = Query("episode_number", description="Sort field: episode_number, created_at, duration_seconds"),
	sort_order: str = Query("asc", description="Sort direction: asc or desc"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	List episodes with optional search, filtering, sorting, and pagination.

	Supports text search on title/description, date range, tag, duration,
	and TTS config filters. All parameters are optional and backward compatible.
	Automatically filtered by user's tenant via RLS.

	Args:
		project_id: Optional project ID to filter by
		status: Optional generation status to filter by
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		search: Optional text to search title and description (case-insensitive)
		date_from: Optional start of date range (ISO 8601)
		date_to: Optional end of date range (ISO 8601)
		tags: Optional comma-separated tags to filter by (AND logic)
		tts_config_id: Optional TTS configuration UUID to filter by
		min_duration: Optional minimum duration in seconds
		max_duration: Optional maximum duration in seconds
		sort_by: Field to sort by (episode_number, created_at, duration_seconds)
		sort_order: Sort direction (asc, desc)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of episodes with metadata

	Raises:
		HTTPException: 422 if sort_by or sort_order is invalid
	"""
	if sort_by not in VALID_SORT_FIELDS:
		raise HTTPException(
			status_code=422,
			detail=f"Invalid sort_by value '{sort_by}'. Must be one of: {', '.join(sorted(VALID_SORT_FIELDS))}"
		)
	if sort_order not in VALID_SORT_ORDERS:
		raise HTTPException(
			status_code=422,
			detail=f"Invalid sort_order value '{sort_order}'. Must be one of: {', '.join(sorted(VALID_SORT_ORDERS))}"
		)

	# Parse comma-separated tags into a list
	tags_list: Optional[List[str]] = None
	if tags:
		tags_list = [t.strip() for t in tags.split(",") if t.strip()]

	skip = (page - 1) * page_size
	episodes, total = await get_episodes(
		db=db,
		project_id=project_id,
		skip=skip,
		limit=page_size,
		status_filter=status,
		search=search,
		date_from=date_from,
		date_to=date_to,
		tags=tags_list,
		tts_config_id=tts_config_id,
		min_duration=min_duration,
		max_duration=max_duration,
		sort_by=sort_by,
		sort_order=sort_order,
	)

	total_pages = (total + page_size - 1) // page_size  # Ceiling division

	return EpisodeListResponse(
		episodes=episodes,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages
	)


@router.post("/batch", response_model=BatchEpisodeResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_create_episodes_endpoint(
	batch_data: BatchEpisodeCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Create multiple episodes in a single batch request (max 50).

	Processes each episode individually and supports partial success:
	valid episodes are created even when some fail. Returns 202 Accepted
	with per-episode results and overall counts.

	Args:
		batch_data: List of episode creation payloads (1-50 items)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Batch result with batch_id, status, counts, and per-episode results

	Raises:
		HTTPException: 402 if the batch would exceed the plan's monthly episode limit
	"""
	# Gate the whole batch up front (conservative: counts every requested episode),
	# then track only those that actually succeeded.
	if not await usage_service.check_episode_quota(db, current_user.id, len(batch_data.episodes)):
		raise HTTPException(
			status_code=status.HTTP_402_PAYMENT_REQUIRED,
			detail="This batch would exceed your plan's monthly episode limit. Please upgrade.",
		)

	result = await batch_create_episodes(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		batch_data=batch_data
	)
	await usage_service.track_episode_creation(
		db, current_user.id, current_user.tenant_id, count=result["created_count"]
	)
	return result


@router.get("/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Get episode details by ID.

	Returns 404 if episode doesn't exist or belongs to different tenant.
	RLS automatically ensures tenant isolation.

	Args:
		episode_id: UUID of episode to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Episode details with all fields

	Raises:
		HTTPException: 404 if episode not found or different tenant
	"""
	episode = await get_episode_by_id(db=db, episode_id=episode_id)

	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)

	return episode


@router.put("/{episode_id}", response_model=EpisodeResponse)
async def update_episode_endpoint(
	episode_id: UUID,
	update_data: EpisodeUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Update episode with partial data.

	Only provided fields are updated (partial updates supported).
	Returns 404 if episode not found or belongs to different tenant.

	Args:
		episode_id: UUID of episode to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated episode with all fields

	Raises:
		HTTPException: 404 if episode not found or different tenant
	"""
	episode = await get_episode_by_id(db=db, episode_id=episode_id)

	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)

	updated_episode = await update_episode(
		db=db,
		episode=episode,
		update_data=update_data
	)

	return updated_episode


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode_endpoint(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Delete episode (hard delete).

	Permanently removes episode and cascades to related content sources.
	Returns 404 if episode not found or belongs to different tenant.

	Args:
		episode_id: UUID of episode to delete
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if episode not found or different tenant
	"""
	episode = await get_episode_by_id(db=db, episode_id=episode_id)

	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)

	await delete_episode(db=db, episode=episode)
	return None  # 204 No Content


@router.get("/{episode_id}/download", response_class=StreamingResponse)
async def download_episode_audio(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
	range: Optional[str] = Header(None)
) -> StreamingResponse:
	"""
	Download podcast audio file with streaming and resume support.

	Streams audio from S3 directly to the client. Supports HTTP Range
	requests (RFC 7233) for resume capability.

	Returns proper Content-Disposition, Content-Type, Accept-Ranges,
	and Cache-Control headers for browser download.

	Args:
		episode_id: UUID of episode to download.
		current_user: Authenticated user (from JWT token).
		db: Database session.
		range: Optional HTTP Range header (e.g., "bytes=0-1023").

	Returns:
		StreamingResponse (200 OK or 206 Partial Content) with audio file.

	Raises:
		HTTPException: 404 if episode not found.
		HTTPException: 403 if episode not complete or audio file missing.
		HTTPException: 416 if Range header is invalid or out of bounds.
	"""
	episode = await get_episode_by_id(db=db, episode_id=episode_id)

	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)

	if episode.generation_status != "complete":
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail=f"Episode not ready for download. Status: {episode.generation_status}"
		)

	# Prefer S3 when an object key exists; otherwise fall back to local disk
	# (no-S3 deployments persist the artifact to LOCAL_AUDIO_STORAGE_PATH — #292).
	has_s3 = bool(episode.s3_key)
	# Only serve local files that live under the configured audio store, so a
	# bad/corrupted file_path can't expose an arbitrary local file (issue #292).
	has_local = (
		bool(episode.file_path)
		and is_within_dir(episode.file_path, settings.LOCAL_AUDIO_STORAGE_PATH)
		and os.path.isfile(episode.file_path)
	)

	if not has_s3 and not has_local:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode audio file not found in storage"
		)

	filename = get_episode_filename(episode)
	http_status = 200
	start_byte = 0
	extra_headers = {}

	if has_s3:
		storage = StorageService()
		head_response = storage.s3_client.head_object(
			Bucket=storage.bucket_name,
			Key=episode.s3_key
		)
		total_size = head_response["ContentLength"]
	else:
		total_size = os.path.getsize(episode.file_path)

	content_length = total_size

	if range:
		# Parse range header - return 416 on invalid range
		try:
			start_byte, end_byte = parse_range_header(range, total_size)
		except ValueError:
			raise HTTPException(
				status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
				detail="Invalid Range header",
				headers={"Content-Range": f"bytes */{total_size}"}
			)

		http_status = 206
		content_length = end_byte - start_byte + 1
		extra_headers["Content-Range"] = f"bytes {start_byte}-{end_byte}/{total_size}"

	if has_s3:
		if range:
			s3_response = storage.s3_client.get_object(
				Bucket=storage.bucket_name,
				Key=episode.s3_key,
				Range=f"bytes={start_byte}-{end_byte}"
			)
		else:
			s3_response = storage.s3_client.get_object(
				Bucket=storage.bucket_name,
				Key=episode.s3_key
			)
		content = iter_s3_body(s3_response["Body"])
	else:
		end_arg = end_byte if range else None
		content = iter_local_file(episode.file_path, start=start_byte, end=end_arg)

	response_headers = {
		"Content-Disposition": f'attachment; filename="{filename}"',
		"Content-Length": str(content_length),
		"Accept-Ranges": "bytes",
		"Cache-Control": "private, max-age=31536000",
		**extra_headers
	}

	return StreamingResponse(
		content=content,
		status_code=http_status,
		headers=response_headers,
		media_type="audio/mpeg"
	)
