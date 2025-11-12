"""
Content source router for RESTful API endpoints.

Provides CRUD operations for content sources with pagination, episode filtering,
and extraction status management. All endpoints require authentication and
automatically enforce tenant isolation via RLS.

Note: Content sources are nested under episodes at /episodes/{episode_id}/content
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User, Episode
from ..schemas.content import (
    ContentSourceCreate,
    ContentSourceUpdate,
    ContentSourceResponse,
    ContentSourceListResponse
)
from ..services.content_service import (
    add_content_source,
    get_content_sources,
    get_content_source_by_id,
    update_content_source,
    delete_content_source
)

router = APIRouter(tags=["content"])


@router.post(
    "/episodes/{episode_id}/content",
    response_model=ContentSourceResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_content_source(
    episode_id: UUID,
    content_data: ContentSourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new content source for episode.

    Validates episode exists and belongs to user's tenant.
    Validates source_data structure based on source_type.
    Requires authentication. Initial extraction_status is 'pending'.

    Args:
        episode_id: UUID of parent episode
        content_data: Content source creation data with source_type and source_data
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Created content source with all fields

    Raises:
        HTTPException: 404 if episode not found
        HTTPException: 422 if source_data validation fails
    """
    # Verify episode_id in path matches episode_id in body
    if content_data.episode_id != episode_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode ID in path must match episode_id in request body"
        )

    # Verify episode exists and user has access
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found"
        )

    content_source = await add_content_source(
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        content_data=content_data
    )
    return content_source


@router.get(
    "/episodes/{episode_id}/content",
    response_model=ContentSourceListResponse
)
async def list_content_sources(
    episode_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List content sources for an episode with pagination.

    Automatically filtered by user's tenant via RLS.
    Results ordered by created_at ascending.
    Validates episode ownership before listing.

    Args:
        episode_id: UUID of parent episode
        page: Page number (1-indexed)
        page_size: Items per page (1-100)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Paginated list of content sources with metadata

    Raises:
        HTTPException: 404 if episode not found or different tenant
    """
    # Verify episode exists and user has access
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found"
        )

    skip = (page - 1) * page_size
    content_sources, total = await get_content_sources(
        db=db,
        episode_id=episode_id,
        skip=skip,
        limit=page_size
    )

    total_pages = (total + page_size - 1) // page_size  # Ceiling division

    return ContentSourceListResponse(
        content_sources=content_sources,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/content/{content_id}", response_model=ContentSourceResponse)
async def get_content_source(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get content source details by ID.

    Returns 404 if content source doesn't exist or belongs to different tenant.
    RLS automatically ensures tenant isolation.

    Args:
        content_id: UUID of content source to retrieve
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Content source details with all fields

    Raises:
        HTTPException: 404 if content source not found or different tenant
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    return content_source


@router.put("/content/{content_id}", response_model=ContentSourceResponse)
async def update_content_source_endpoint(
    content_id: UUID,
    update_data: ContentSourceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update content source with partial data.

    Only provided fields are updated (partial updates supported).
    Returns 404 if content source not found or belongs to different tenant.

    Args:
        content_id: UUID of content source to update
        update_data: Update data (only provided fields will be updated)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Updated content source with all fields

    Raises:
        HTTPException: 404 if content source not found or different tenant
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    updated_content_source = await update_content_source(
        db=db,
        content_source=content_source,
        update_data=update_data
    )

    return updated_content_source


@router.delete("/content/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_source_endpoint(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete content source (hard delete).

    Permanently removes content source.
    Returns 404 if content source not found or belongs to different tenant.

    Args:
        content_id: UUID of content source to delete
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if content source not found or different tenant
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    await delete_content_source(db=db, content_source=content_source)
    return None  # 204 No Content
