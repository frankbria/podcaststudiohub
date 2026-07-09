"""
Episode layout service layer for business logic.

Provides CRUD operations for episode layouts with snippet validation,
tenant isolation, default layout management, and referential integrity checks.
RLS ensures tenant isolation at the database level.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from typing import Optional
from fastapi import HTTPException, status

from ..models import EpisodeLayout, AudioSnippet, EpisodeComposition, Project
from ..schemas.episode_layout import EpisodeLayoutCreate, EpisodeLayoutUpdate, LayoutConfig


async def validate_snippet_references(
	db: AsyncSession,
	layout_config: LayoutConfig,
	tenant_id: UUID
) -> None:
	"""
	Verify all snippet_id references in layout_config exist and belong to tenant.

	Args:
		db: Database session
		layout_config: Layout configuration to validate
		tenant_id: Tenant ID to verify ownership

	Raises:
		HTTPException: 422 if any snippet is not found or belongs to different tenant
	"""
	snippet_ids = [
		s.snippet_id
		for s in layout_config.segments
		if s.type == "snippet" and s.snippet_id is not None
	]

	if not snippet_ids:
		return

	for snippet_id in snippet_ids:
		result = await db.execute(
			select(AudioSnippet).where(
				AudioSnippet.id == snippet_id,
				AudioSnippet.tenant_id == tenant_id
			)
		)
		snippet = result.scalar_one_or_none()
		if snippet is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail=f"Snippet '{snippet_id}' not found in your tenant"
			)


async def _unset_other_defaults(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	project_id: Optional[UUID],
	exclude_id: Optional[UUID] = None
) -> None:
	"""
	Unset is_default for all other layouts in the same scope.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
		project_id: Optional project scope
		exclude_id: Layout ID to exclude from update (the one being set as default)
	"""
	query = select(EpisodeLayout).where(
		EpisodeLayout.tenant_id == tenant_id,
		EpisodeLayout.is_default == True  # noqa: E712
	)

	if project_id is not None:
		query = query.where(EpisodeLayout.project_id == project_id)
	else:
		query = query.where(EpisodeLayout.project_id == None)  # noqa: E711

	if exclude_id is not None:
		query = query.where(EpisodeLayout.id != exclude_id)

	result = await db.execute(query)
	existing_defaults = result.scalars().all()

	for layout in existing_defaults:
		layout.is_default = False


async def create_episode_layout(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	layout_data: EpisodeLayoutCreate
) -> EpisodeLayout:
	"""
	Create a new episode layout.

	Validates project_id if provided, manages default flag, and persists the layout.

	Args:
		db: Database session
		user_id: ID of user creating the layout
		tenant_id: Tenant ID for isolation
		layout_data: Layout creation data

	Returns:
		Created EpisodeLayout instance

	Raises:
		HTTPException: 404 if project not found
	"""
	# Validate project_id if provided (RLS ensures it's in correct tenant)
	if layout_data.project_id is not None:
		project = await db.get(Project, layout_data.project_id)
		if project is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Project not found"
			)

	# Unset other defaults if this layout is being set as default
	if layout_data.is_default:
		await _unset_other_defaults(
			db=db,
			user_id=user_id,
			tenant_id=tenant_id,
			project_id=layout_data.project_id
		)

	layout = EpisodeLayout(
		user_id=user_id,
		tenant_id=tenant_id,
		project_id=layout_data.project_id,
		name=layout_data.name,
		description=layout_data.description,
		layout_config=layout_data.layout_config.model_dump(),
		is_default=layout_data.is_default
	)
	db.add(layout)
	await db.commit()
	return layout


async def get_episode_layouts(
	db: AsyncSession,
	project_id: Optional[UUID] = None,
	skip: int = 0,
	limit: int = 20
) -> tuple[list[EpisodeLayout], int]:
	"""
	Get paginated list of episode layouts.

	Optionally filter by project_id. RLS automatically filters by tenant.

	Args:
		db: Database session
		project_id: Optional project ID to filter by
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return

	Returns:
		Tuple of (layouts list, total count)
	"""
	query = select(EpisodeLayout)

	if project_id is not None:
		query = query.where(EpisodeLayout.project_id == project_id)

	# Get total count before pagination
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	# Get paginated results ordered by created_at desc
	query = query.offset(skip).limit(limit).order_by(
		EpisodeLayout.created_at.desc()
	)
	result = await db.execute(query)
	layouts = result.scalars().all()

	return list(layouts), total


async def get_episode_layout_by_id(
	db: AsyncSession,
	layout_id: UUID
) -> Optional[EpisodeLayout]:
	"""
	Get episode layout by ID.

	RLS ensures user can only access layouts within their tenant.
	Returns None if layout doesn't exist or belongs to different tenant.

	Args:
		db: Database session
		layout_id: UUID of layout to retrieve

	Returns:
		EpisodeLayout instance or None if not found
	"""
	result = await db.execute(
		select(EpisodeLayout).where(EpisodeLayout.id == layout_id)
	)
	return result.scalar_one_or_none()


async def update_episode_layout(
	db: AsyncSession,
	layout: EpisodeLayout,
	update_data: EpisodeLayoutUpdate
) -> EpisodeLayout:
	"""
	Update episode layout with partial data.

	Only updates fields provided in update_data (partial updates supported).
	Manages default flag if is_default is set to True.

	Args:
		db: Database session
		layout: Existing EpisodeLayout instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated EpisodeLayout instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)

	# Handle is_default: unset others if being set to True
	if update_dict.get("is_default") is True:
		await _unset_other_defaults(
			db=db,
			user_id=layout.user_id,
			tenant_id=layout.tenant_id,
			project_id=layout.project_id,
			exclude_id=layout.id
		)

	for field, value in update_dict.items():
		setattr(layout, field, value)

	await db.commit()
	return layout


async def delete_episode_layout(
	db: AsyncSession,
	layout: EpisodeLayout
) -> None:
	"""
	Delete episode layout.

	Checks if layout is referenced by any EpisodeComposition before deletion.
	Raises 409 Conflict if layout is in use.

	Args:
		db: Database session
		layout: EpisodeLayout instance to delete

	Raises:
		HTTPException: 409 if layout is referenced by episode compositions
	"""
	# Check if layout is referenced by any composition
	result = await db.execute(
		select(func.count()).where(EpisodeComposition.layout_id == layout.id)
	)
	ref_count = result.scalar()

	if ref_count and ref_count > 0:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"Cannot delete: {ref_count} episode composition(s) use this layout"
		)

	await db.delete(layout)
	await db.commit()
