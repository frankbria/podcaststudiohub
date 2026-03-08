"""
Episode layout router for RESTful API endpoints.

Provides CRUD operations for episode layouts with pagination, project filtering,
snippet reference validation, and default layout management. All endpoints require
authentication and automatically enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.episode_layout import (
	EpisodeLayoutCreate,
	EpisodeLayoutUpdate,
	EpisodeLayoutResponse,
	EpisodeLayoutListResponse
)
from ..services.episode_layout_service import (
	create_episode_layout,
	get_episode_layouts,
	get_episode_layout_by_id,
	update_episode_layout,
	delete_episode_layout,
	validate_snippet_references
)

router = APIRouter(prefix="/episode-layouts", tags=["episode-layouts"])


@router.post("", response_model=EpisodeLayoutResponse, status_code=status.HTTP_201_CREATED)
async def create_episode_layout_endpoint(
	layout_data: EpisodeLayoutCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Create new episode layout.

	Validates all referenced snippet IDs exist and belong to user's tenant.
	Exactly one main_content segment is required in layout_config.
	If is_default=True, all other layouts in same scope are unset as default.

	Args:
		layout_data: Layout creation data with name, config, and optional project_id
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created layout with all fields

	Raises:
		HTTPException: 404 if project not found
		HTTPException: 422 if snippet references are invalid
	"""
	# Validate snippet references before creation
	await validate_snippet_references(
		db=db,
		layout_config=layout_data.layout_config,
		tenant_id=current_user.tenant_id
	)

	layout = await create_episode_layout(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		layout_data=layout_data
	)
	return layout


@router.get("", response_model=EpisodeLayoutListResponse)
async def list_episode_layouts(
	project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	List episode layouts with optional filtering and pagination.

	Optionally filter by project_id. Automatically filtered by user's tenant via RLS.
	Results ordered by created_at descending.

	Args:
		project_id: Optional project ID to filter by
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of episode layouts with metadata
	"""
	skip = (page - 1) * page_size
	layouts, total = await get_episode_layouts(
		db=db,
		project_id=project_id,
		skip=skip,
		limit=page_size
	)

	total_pages = (total + page_size - 1) // page_size  # Ceiling division

	return EpisodeLayoutListResponse(
		layouts=layouts,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages
	)


@router.get("/{layout_id}", response_model=EpisodeLayoutResponse)
async def get_episode_layout(
	layout_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Get episode layout details by ID.

	Returns 404 if layout doesn't exist or belongs to different tenant.
	RLS automatically ensures tenant isolation.

	Args:
		layout_id: UUID of layout to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Layout details with all fields

	Raises:
		HTTPException: 404 if layout not found or different tenant
	"""
	layout = await get_episode_layout_by_id(db=db, layout_id=layout_id)

	if layout is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode layout not found"
		)

	return layout


@router.put("/{layout_id}", response_model=EpisodeLayoutResponse)
async def update_episode_layout_endpoint(
	layout_id: UUID,
	update_data: EpisodeLayoutUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Update episode layout with partial data.

	Only provided fields are updated (partial updates supported).
	If layout_config is updated, validates snippet references.
	Returns 404 if layout not found or belongs to different tenant.

	Args:
		layout_id: UUID of layout to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated layout with all fields

	Raises:
		HTTPException: 404 if layout not found or different tenant
		HTTPException: 422 if snippet references are invalid
	"""
	layout = await get_episode_layout_by_id(db=db, layout_id=layout_id)

	if layout is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode layout not found"
		)

	# Validate new snippet references if layout_config is being updated
	if update_data.layout_config is not None:
		await validate_snippet_references(
			db=db,
			layout_config=update_data.layout_config,
			tenant_id=current_user.tenant_id
		)

	updated_layout = await update_episode_layout(
		db=db,
		layout=layout,
		update_data=update_data
	)

	return updated_layout


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode_layout_endpoint(
	layout_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Delete episode layout.

	Returns 404 if layout not found or belongs to different tenant.
	Returns 409 if layout is referenced by active episode compositions.

	Args:
		layout_id: UUID of layout to delete
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if layout not found or different tenant
		HTTPException: 409 if layout is in use by episode compositions
	"""
	layout = await get_episode_layout_by_id(db=db, layout_id=layout_id)

	if layout is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode layout not found"
		)

	await delete_episode_layout(db=db, layout=layout)
	return None  # 204 No Content


@router.post("/{layout_id}/set-default", response_model=EpisodeLayoutResponse)
async def set_default_episode_layout(
	layout_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Set layout as default for the tenant.

	Sets is_default=True for the specified layout and unsets all other layouts
	in the same scope (same project_id or global if no project).
	Returns 404 if layout not found or belongs to different tenant.

	Args:
		layout_id: UUID of layout to set as default
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated layout with is_default=True

	Raises:
		HTTPException: 404 if layout not found or different tenant
	"""
	layout = await get_episode_layout_by_id(db=db, layout_id=layout_id)

	if layout is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode layout not found"
		)

	set_default_data = EpisodeLayoutUpdate(is_default=True)
	updated_layout = await update_episode_layout(
		db=db,
		layout=layout,
		update_data=set_default_data
	)

	return updated_layout
