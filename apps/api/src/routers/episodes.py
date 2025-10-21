"""Episodes router for podcast episode management"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..schemas.episode import EpisodeCreate, EpisodeUpdate, EpisodeResponse
from ..schemas.common import PaginationParams, PaginatedResponse
from ..models.episode import Episode
from ..models.content_source import ContentSource
from ..models.project import Project
from ..models.user import User
from ..dependencies import get_current_user

router = APIRouter(prefix="/episodes", tags=["Episodes"])


@router.get("/projects/{project_id}/episodes", response_model=PaginatedResponse[EpisodeResponse])
async def list_project_episodes(
    project_id: UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all episodes for a project"""
    # Verify project belongs to user
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Count total episodes
    count_query = select(func.count()).select_from(Episode).where(Episode.project_id == project_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated episodes
    query = (
        select(Episode)
        .where(Episode.project_id == project_id)
        .order_by(Episode.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    result = await db.execute(query)
    episodes = result.scalars().all()

    # Add content source count
    episodes_data = []
    for episode in episodes:
        content_count_query = select(func.count()).select_from(ContentSource).where(ContentSource.episode_id == episode.id)
        content_count_result = await db.execute(content_count_query)
        content_count = content_count_result.scalar()

        episode_dict = EpisodeResponse.model_validate(episode).model_dump()
        episode_dict["content_source_count"] = content_count
        episodes_data.append(EpisodeResponse(**episode_dict))

    return PaginatedResponse(
        items=episodes_data,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.post("/projects/{project_id}/episodes", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
async def create_episode(
    project_id: UUID,
    episode_data: EpisodeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new episode"""
    # Verify project belongs to user
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    episode = Episode(
        project_id=project_id,
        tenant_id=current_user.tenant_id,
        title=episode_data.title,
        description=episode_data.description,
        episode_number=episode_data.episode_number,
        generation_status='draft',
        generation_progress={},
        metadata={},
    )

    db.add(episode)
    await db.commit()
    await db.refresh(episode)

    episode_dict = EpisodeResponse.model_validate(episode).model_dump()
    episode_dict["content_source_count"] = 0
    return EpisodeResponse(**episode_dict)


@router.get("/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
    episode_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific episode"""
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Get content source count
    content_count_query = select(func.count()).select_from(ContentSource).where(ContentSource.episode_id == episode.id)
    content_count_result = await db.execute(content_count_query)
    content_count = content_count_result.scalar()

    episode_dict = EpisodeResponse.model_validate(episode).model_dump()
    episode_dict["content_source_count"] = content_count
    return EpisodeResponse(**episode_dict)


@router.patch("/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    episode_id: UUID,
    episode_data: EpisodeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an episode"""
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Update fields
    if episode_data.title is not None:
        episode.title = episode_data.title
    if episode_data.description is not None:
        episode.description = episode_data.description
    if episode_data.episode_number is not None:
        episode.episode_number = episode_data.episode_number
    if episode_data.episode_metadata is not None:
        episode.episode_metadata = episode_data.episode_metadata.model_dump()

    await db.commit()
    await db.refresh(episode)

    # Get content source count
    content_count_query = select(func.count()).select_from(ContentSource).where(ContentSource.episode_id == episode.id)
    content_count_result = await db.execute(content_count_query)
    content_count = content_count_result.scalar()

    episode_dict = EpisodeResponse.model_validate(episode).model_dump()
    episode_dict["content_source_count"] = content_count
    return EpisodeResponse(**episode_dict)


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode(
    episode_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an episode"""
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    await db.delete(episode)
    await db.commit()
