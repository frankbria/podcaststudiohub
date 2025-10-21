"""Content sources router for episode content management"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..schemas.content import ContentSourceCreate, ContentSourceResponse
from ..models.content_source import ContentSource
from ..models.episode import Episode
from ..models.user import User
from ..dependencies import get_current_user

router = APIRouter(prefix="/content", tags=["Content Sources"])


@router.get("/episodes/{episode_id}/content", response_model=List[ContentSourceResponse])
async def list_episode_content(
    episode_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all content sources for an episode"""
    # Verify episode belongs to user's tenant
    episode_result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    if not episode_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Get content sources
    result = await db.execute(
        select(ContentSource).where(ContentSource.episode_id == episode_id).order_by(ContentSource.created_at.asc())
    )
    content_sources = result.scalars().all()

    return content_sources


@router.post("/episodes/{episode_id}/content", response_model=ContentSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_content_source(
    episode_id: UUID,
    content_data: ContentSourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a content source to an episode"""
    # Verify episode belongs to user's tenant
    episode_result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    if not episode_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    content_source = ContentSource(
        episode_id=episode_id,
        tenant_id=current_user.tenant_id,
        source_type=content_data.source_type,
        source_data=content_data.source_data,
        extraction_metadata={},
    )

    db.add(content_source)
    await db.commit()
    await db.refresh(content_source)

    return content_source
