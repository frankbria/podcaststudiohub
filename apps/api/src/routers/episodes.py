"""
Episode router for RESTful API endpoints.

Provides CRUD operations for podcast episodes with pagination, project filtering,
status filtering, and generation management. All endpoints require authentication
and automatically enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List
from datetime import datetime

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.episode import (
	EpisodeCreate,
	EpisodeUpdate,
	EpisodeResponse,
	EpisodeListResponse
)
from ..services.episode_service import (
	create_episode,
	get_episodes,
	get_episode_by_id,
	update_episode,
	delete_episode,
	VALID_SORT_FIELDS,
	VALID_SORT_ORDERS
)
from ..services.storage_service import StorageService
from ..utils.download_utils import get_episode_filename, parse_range_header, iter_s3_body

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
		HTTPException: 404 if project not found
	"""
	episode = await create_episode(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		episode_data=episode_data
	)
	return episode


@router.get("", response_model=EpisodeListResponse)
async def list_episodes(
	project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
	status: Optional[str] = Query(None, description="Filter by generation status"),
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	search: Optional[str] = Query(None, description="Full-text search on title and description"),
	date_from: Optional[datetime] = Query(None, description="Filter episodes created on or after this date (ISO 8601)"),
	date_to: Optional[datetime] = Query(None, description="Filter episodes created on or before this date (ISO 8601)"),
	tags: Optional[str] = Query(None, description="Comma-separated tags to filter by (OR logic)"),
	min_duration: Optional[float] = Query(None, ge=0, description="Minimum duration in seconds"),
	max_duration: Optional[float] = Query(None, ge=0, description="Maximum duration in seconds"),
	sort_by: str = Query("episode_number", description="Sort field: episode_number, created_at, duration_seconds"),
	sort_order: str = Query("asc", description="Sort direction: asc or desc"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	List episodes with optional search, filtering, and pagination.

	Filter by project_id and/or generation_status, search by title/description,
	filter by date range, tags, or duration. Automatically filtered by user's
	tenant via RLS.

	Args:
		project_id: Optional project ID to filter by
		status: Optional generation status to filter by
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		search: Optional full-text search on title and description
		date_from: Optional start date filter (inclusive, based on created_at)
		date_to: Optional end date filter (inclusive, based on created_at)
		tags: Optional comma-separated tags to filter by (OR logic)
		min_duration: Optional minimum duration in seconds
		max_duration: Optional maximum duration in seconds
		sort_by: Sort field (episode_number, created_at, duration_seconds)
		sort_order: Sort direction (asc, desc)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of episodes with metadata
	"""
	if sort_by not in VALID_SORT_FIELDS:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=f"Invalid sort_by value '{sort_by}'. Must be one of: {', '.join(sorted(VALID_SORT_FIELDS))}"
		)
	if sort_order not in VALID_SORT_ORDERS:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=f"Invalid sort_order value '{sort_order}'. Must be one of: {', '.join(sorted(VALID_SORT_ORDERS))}"
		)

	# Parse comma-separated tags
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
		min_duration=min_duration,
		max_duration=max_duration,
		sort_by=sort_by,
		sort_order=sort_order
	)

	total_pages = (total + page_size - 1) // page_size  # Ceiling division

	return EpisodeListResponse(
		episodes=episodes,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages
	)


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

	if not episode.s3_key:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode audio file not found in storage"
		)

	storage = StorageService()

	# Get file metadata from S3
	head_response = storage.s3_client.head_object(
		Bucket=storage.bucket_name,
		Key=episode.s3_key
	)
	total_size = head_response["ContentLength"]

	filename = get_episode_filename(episode)
	http_status = 200
	start_byte = 0
	content_length = total_size
	extra_headers = {}

	if range:
		# Parse range header - return 416 on invalid range
		try:
			start_byte, end_byte = parse_range_header(range, total_size)
		except ValueError:
			raise HTTPException(
				status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
				detail="Invalid Range header",
				headers={"Content-Range": f"bytes */{total_size}"}
			)

		http_status = 206
		content_length = end_byte - start_byte + 1
		extra_headers["Content-Range"] = f"bytes {start_byte}-{end_byte}/{total_size}"

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

	body = s3_response["Body"]

	response_headers = {
		"Content-Disposition": f'attachment; filename="{filename}"',
		"Content-Length": str(content_length),
		"Accept-Ranges": "bytes",
		"Cache-Control": "private, max-age=31536000",
		**extra_headers
	}

	return StreamingResponse(
		content=iter_s3_body(body),
		status_code=http_status,
		headers=response_headers,
		media_type="audio/mpeg"
	)
