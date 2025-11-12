"""
Project router for RESTful API endpoints.

Provides CRUD operations for podcast projects with pagination, validation,
and soft delete functionality. All endpoints require authentication and
automatically enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.project import (
	ProjectCreate,
	ProjectUpdate,
	ProjectResponse,
	ProjectListResponse
)
from ..services.project_service import (
	create_project,
	get_projects,
	get_project_by_id,
	update_project,
	archive_project
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project_endpoint(
	project_data: ProjectCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Create new podcast project.

	Requires authentication. Project automatically assigned to user's tenant.
	RLS ensures tenant isolation automatically.

	Args:
		project_data: Project creation data with name, description, and podcast_metadata
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created project with all fields
	"""
	project = await create_project(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		project_data=project_data
	)
	return project


@router.get("", response_model=ProjectListResponse)
async def list_projects(
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	include_archived: bool = Query(False, description="Include archived projects"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	List projects with pagination.

	Automatically filtered by user's tenant via RLS. Excludes archived
	projects by default unless include_archived=True.

	Args:
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		include_archived: Whether to include archived projects
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of projects with metadata
	"""
	skip = (page - 1) * page_size
	projects, total = await get_projects(
		db=db,
		skip=skip,
		limit=page_size,
		include_archived=include_archived
	)

	total_pages = (total + page_size - 1) // page_size  # Ceiling division

	return ProjectListResponse(
		projects=projects,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages
	)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Get project details by ID.

	Returns 404 if project doesn't exist or belongs to different tenant.
	RLS automatically ensures tenant isolation.

	Args:
		project_id: UUID of project to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Project details with all fields

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	project = await get_project_by_id(db=db, project_id=project_id)

	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found"
		)

	return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project_endpoint(
	project_id: UUID,
	update_data: ProjectUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Update project with partial data.

	Only provided fields are updated (partial updates supported).
	Returns 404 if project not found or belongs to different tenant.

	Args:
		project_id: UUID of project to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated project with all fields

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	project = await get_project_by_id(db=db, project_id=project_id)

	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found"
		)

	updated_project = await update_project(
		db=db,
		project=project,
		update_data=update_data
	)

	return updated_project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Archive project (soft delete).

	Sets is_archived=True. Project can be restored by updating is_archived=False.
	Returns 404 if project not found or belongs to different tenant.

	Args:
		project_id: UUID of project to archive
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	project = await get_project_by_id(db=db, project_id=project_id)

	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found"
		)

	await archive_project(db=db, project=project)
	return None  # 204 No Content
