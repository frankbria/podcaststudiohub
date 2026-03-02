"""
Content source service layer for business logic.

Provides CRUD operations for content sources with episode validation, pagination,
and extraction status management. RLS ensures tenant isolation.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from typing import Optional
from fastapi import HTTPException, status

from ..models import ContentSource, Episode
from ..schemas.content import ContentSourceCreate, ContentSourceUpdate


async def add_content_source(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    content_data: ContentSourceCreate
) -> ContentSource:
    """
    Create new content source for episode.

    Validates episode exists and belongs to user's tenant (RLS).
    Initial extraction_status is set to 'pending'.

    Args:
        db: Database session
        user_id: ID of user creating the content source (not stored directly)
        tenant_id: Tenant ID for isolation
        content_data: Content source creation data

    Returns:
        Created ContentSource instance

    Raises:
        HTTPException: 404 if episode not found
    """
    # Verify episode exists (RLS ensures it's in correct tenant)
    episode = await db.get(Episode, content_data.episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found"
        )

    content_source = ContentSource(
        episode_id=content_data.episode_id,
        tenant_id=tenant_id,
        source_type=content_data.source_type,
        source_data=content_data.source_data,
        extraction_status="pending",  # Initial status
        extracted_content=None,
        error_message=None
    )
    db.add(content_source)
    await db.commit()
    return content_source


async def get_content_sources(
    db: AsyncSession,
    episode_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> tuple[list[ContentSource], int]:
    """
    Get paginated list of content sources for an episode.

    RLS automatically filters by tenant.
    Results ordered by created_at ascending.

    Args:
        db: Database session
        episode_id: Episode ID to filter by
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return

    Returns:
        Tuple of (content sources list, total count)
    """
    # Build query filtered by episode_id
    query = select(ContentSource).where(ContentSource.episode_id == episode_id)

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated results, ordered by created_at
    query = query.offset(skip).limit(limit).order_by(
        ContentSource.created_at.asc()
    )
    result = await db.execute(query)
    content_sources = result.scalars().all()

    return list(content_sources), total


async def get_content_source_by_id(
    db: AsyncSession,
    content_id: UUID
) -> Optional[ContentSource]:
    """
    Get content source by ID.

    RLS ensures user can only access content sources within their tenant.
    Returns None if content source doesn't exist or belongs to different tenant.

    Args:
        db: Database session
        content_id: UUID of content source to retrieve

    Returns:
        ContentSource instance or None if not found
    """
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == content_id)
    )
    return result.scalar_one_or_none()


async def update_content_source(
    db: AsyncSession,
    content_source: ContentSource,
    update_data: ContentSourceUpdate
) -> ContentSource:
    """
    Update content source with partial data.

    Only updates fields provided in update_data (partial updates supported).
    Uses Pydantic's model_dump(exclude_unset=True) to only update provided fields.

    Args:
        db: Database session
        content_source: Existing content source instance
        update_data: Update data (only provided fields will be updated)

    Returns:
        Updated ContentSource instance
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(content_source, field, value)

    await db.commit()
    return content_source


async def delete_content_source(
    db: AsyncSession,
    content_source: ContentSource
) -> None:
    """
    Hard delete content source.

    Content sources use hard delete (no soft delete).

    Args:
        db: Database session
        content_source: ContentSource instance to delete
    """
    await db.delete(content_source)
    await db.commit()
