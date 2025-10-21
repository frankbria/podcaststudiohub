"""Projects router for podcast project management"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from ..schemas.common import PaginationParams, PaginatedResponse
from ..models.project import Project
from ..models.episode import Episode
from ..models.user import User
from ..dependencies import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects for the current user"""
    # Count total projects
    count_query = select(func.count()).select_from(Project).where(Project.user_id == current_user.id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated projects
    query = (
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    result = await db.execute(query)
    projects = result.scalars().all()

    # Add episode count to each project
    projects_data = []
    for project in projects:
        episode_count_query = select(func.count()).select_from(Episode).where(Episode.project_id == project.id)
        episode_count_result = await db.execute(episode_count_query)
        episode_count = episode_count_result.scalar()

        project_dict = ProjectResponse.model_validate(project).model_dump()
        project_dict["episode_count"] = episode_count
        projects_data.append(ProjectResponse(**project_dict))

    return PaginatedResponse(
        items=projects_data,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project"""
    project = Project(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        title=project_data.title,
        description=project_data.description,
        podcast_metadata=project_data.podcast_metadata.model_dump(),
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    project_dict = ProjectResponse.model_validate(project).model_dump()
    project_dict["episode_count"] = 0
    return ProjectResponse(**project_dict)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific project"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Get episode count
    episode_count_query = select(func.count()).select_from(Episode).where(Episode.project_id == project.id)
    episode_count_result = await db.execute(episode_count_query)
    episode_count = episode_count_result.scalar()

    project_dict = ProjectResponse.model_validate(project).model_dump()
    project_dict["episode_count"] = episode_count
    return ProjectResponse(**project_dict)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a project"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Update fields
    if project_data.title is not None:
        project.title = project_data.title
    if project_data.description is not None:
        project.description = project_data.description
    if project_data.podcast_metadata is not None:
        project.podcast_metadata = project_data.podcast_metadata.model_dump()

    await db.commit()
    await db.refresh(project)

    # Get episode count
    episode_count_query = select(func.count()).select_from(Episode).where(Episode.project_id == project.id)
    episode_count_result = await db.execute(episode_count_query)
    episode_count = episode_count_result.scalar()

    project_dict = ProjectResponse.model_validate(project).model_dump()
    project_dict["episode_count"] = episode_count
    return ProjectResponse(**project_dict)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await db.delete(project)
    await db.commit()
