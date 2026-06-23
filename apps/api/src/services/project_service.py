"""
Project service layer for business logic.

Provides CRUD operations for projects with pagination, validation,
and soft delete functionality. RLS ensures tenant isolation automatically.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from typing import Optional

from ..models import Project
from ..schemas.project import ProjectCreate, ProjectUpdate

# Fields an end user may set through the public update endpoint. Defense-in-depth
# allowlist so a future ProjectUpdate addition (e.g. an ownership/billing column)
# can't silently become mass-assignable. Mirrors EPISODE_USER_EDITABLE_FIELDS.
PROJECT_USER_EDITABLE_FIELDS = {
	"name",
	"description",
	"podcast_metadata",
	"default_tts_config_id",
	"default_template_id",
	"is_archived",
}


async def create_project(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	project_data: ProjectCreate
) -> Project:
	"""
	Create new project for user.

	RLS automatically ensures tenant isolation. The project is created
	with the user's tenant_id and is_archived set to False by default.

	Args:
		db: Database session
		user_id: ID of user creating the project
		tenant_id: Tenant ID for isolation
		project_data: Project creation data

	Returns:
		Created Project instance
	"""
	project = Project(
		name=project_data.name,
		description=project_data.description,
		podcast_metadata=project_data.podcast_metadata,
		user_id=user_id,
		tenant_id=tenant_id,
		is_archived=False
	)
	db.add(project)
	await db.commit()
	return project


async def get_projects(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 20,
	include_archived: bool = False
) -> tuple[list[Project], int]:
	"""
	Get paginated list of projects.

	RLS automatically filters by tenant based on the session's tenant_id.
	Excludes archived projects by default unless include_archived is True.

	Args:
		db: Database session
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return
		include_archived: Whether to include archived projects

	Returns:
		Tuple of (projects list, total count)
	"""
	# Build base query
	query = select(Project)
	if not include_archived:
		query = query.where(Project.is_archived.is_(False))

	# Get total count (before pagination)
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	# Get paginated results, ordered by most recent first
	query = query.offset(skip).limit(limit).order_by(Project.created_at.desc())
	result = await db.execute(query)
	projects = result.scalars().all()

	return list(projects), total


async def get_project_by_id(
	db: AsyncSession,
	project_id: UUID
) -> Optional[Project]:
	"""
	Get project by ID.

	RLS ensures user can only access projects within their tenant.
	Returns None if project doesn't exist or belongs to different tenant.

	Args:
		db: Database session
		project_id: UUID of project to retrieve

	Returns:
		Project instance or None if not found
	"""
	result = await db.execute(
		select(Project).where(Project.id == project_id)
	)
	return result.scalar_one_or_none()


async def update_project(
	db: AsyncSession,
	project: Project,
	update_data: ProjectUpdate
) -> Project:
	"""
	Update project with partial data.

	Only updates fields provided in update_data (partial updates supported).
	Uses Pydantic's exclude_unset to only update provided fields.

	Args:
		db: Database session
		project: Existing project instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated Project instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)
	for field, value in update_dict.items():
		if field not in PROJECT_USER_EDITABLE_FIELDS:
			continue  # never mass-assign non-user-editable fields
		setattr(project, field, value)

	await db.commit()
	return project


async def archive_project(
	db: AsyncSession,
	project: Project
) -> Project:
	"""
	Soft delete project by setting is_archived=True.

	Preserves project data for potential recovery. Archived projects
	are excluded from default queries but can be retrieved with
	include_archived=True.

	Args:
		db: Database session
		project: Project instance to archive

	Returns:
		Archived Project instance
	"""
	project.is_archived = True
	await db.commit()
	return project
