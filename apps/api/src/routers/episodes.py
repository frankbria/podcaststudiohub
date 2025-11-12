"""
Episode router for RESTful API endpoints.

Provides CRUD operations for podcast episodes with pagination, project filtering,
status filtering, and generation management. All endpoints require authentication
and automatically enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

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
	delete_episode
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
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	List episodes with optional filtering and pagination.

	Filter by project_id and/or generation_status.
	Automatically filtered by user's tenant via RLS.
	Results ordered by episode_number ascending.

	Args:
		project_id: Optional project ID to filter by
		status: Optional generation status to filter by
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of episodes with metadata
	"""
	skip = (page - 1) * page_size
	episodes, total = await get_episodes(
		db=db,
		project_id=project_id,
		skip=skip,
		limit=page_size,
		status_filter=status
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
