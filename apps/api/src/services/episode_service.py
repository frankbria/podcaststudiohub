"""
Episode service layer for business logic.

Provides CRUD operations for episodes with project validation, pagination,
status filtering, and generation status management. RLS ensures tenant isolation.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from uuid import UUID
from typing import Optional
from fastapi import HTTPException, status

from ..models import Episode, Project
from ..schemas.episode import EpisodeCreate, EpisodeUpdate


async def create_episode(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	episode_data: EpisodeCreate
) -> Episode:
	"""
	Create new episode for project.

	Validates project exists and belongs to user's tenant (RLS).
	Initial generation_status is set to 'draft'.

	Args:
		db: Database session
		user_id: ID of user creating the episode
		tenant_id: Tenant ID for isolation
		episode_data: Episode creation data

	Returns:
		Created Episode instance

	Raises:
		HTTPException: 404 if project not found
	"""
	# Verify project exists (RLS ensures it's in correct tenant)
	project = await db.get(Project, episode_data.project_id)
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found"
		)

	# Auto-assign episode_number if not provided
	if episode_data.episode_number is None:
		max_result = await db.execute(
			select(func.max(Episode.episode_number)).where(
				Episode.project_id == episode_data.project_id
			)
		)
		max_number = max_result.scalar()
		episode_number = (max_number or 0) + 1
	else:
		episode_number = episode_data.episode_number

	episode = Episode(
		project_id=episode_data.project_id,
		user_id=user_id,
		tenant_id=tenant_id,
		episode_number=episode_number,
		episode_metadata=episode_data.episode_metadata,
		generation_status="draft",  # Initial status
		generation_progress={}  # Empty progress initially
	)
	db.add(episode)
	try:
		await db.commit()
	except IntegrityError as e:
		await db.rollback()
		if 'uq_episodes_project_number' in str(e):
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail=f"Episode number {episode_number} already exists for this project"
			)
		raise
	return episode


async def get_episodes(
	db: AsyncSession,
	project_id: Optional[UUID] = None,
	skip: int = 0,
	limit: int = 20,
	status_filter: Optional[str] = None
) -> tuple[list[Episode], int]:
	"""
	Get paginated list of episodes.

	Optionally filter by project_id and generation_status.
	RLS automatically filters by tenant.

	Args:
		db: Database session
		project_id: Optional project ID to filter by
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return
		status_filter: Optional generation status to filter by

	Returns:
		Tuple of (episodes list, total count)
	"""
	# Build base query
	query = select(Episode)

	if project_id:
		query = query.where(Episode.project_id == project_id)

	if status_filter:
		query = query.where(Episode.generation_status == status_filter)

	# Get total count (before pagination)
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	# Get paginated results, ordered by episode number
	query = query.offset(skip).limit(limit).order_by(
		Episode.episode_number.asc()
	)
	result = await db.execute(query)
	episodes = result.scalars().all()

	return list(episodes), total


async def get_episode_by_id(
	db: AsyncSession,
	episode_id: UUID
) -> Optional[Episode]:
	"""
	Get episode by ID.

	RLS ensures user can only access episodes within their tenant.
	Returns None if episode doesn't exist or belongs to different tenant.

	Args:
		db: Database session
		episode_id: UUID of episode to retrieve

	Returns:
		Episode instance or None if not found
	"""
	result = await db.execute(
		select(Episode).where(Episode.id == episode_id)
	)
	return result.scalar_one_or_none()


async def update_episode(
	db: AsyncSession,
	episode: Episode,
	update_data: EpisodeUpdate
) -> Episode:
	"""
	Update episode with partial data.

	Only updates fields provided in update_data (partial updates supported).
	Uses Pydantic's model_dump(exclude_unset=True) to only update provided fields.
	Triggers RSS feed regeneration when episode status changes to 'complete'.

	Args:
		db: Database session
		episode: Existing episode instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated Episode instance
	"""
	prev_status = episode.generation_status
	update_dict = update_data.model_dump(exclude_unset=True)
	for field, value in update_dict.items():
		setattr(episode, field, value)

	await db.commit()

	# Trigger RSS regeneration when episode becomes complete/published
	new_status = episode.generation_status
	if prev_status != "complete" and new_status == "complete":
		await _trigger_rss_update(episode)

	return episode


async def _trigger_rss_update(episode: Episode) -> None:
	"""
	Enqueue RSS feed regeneration task when an episode is published.

	Silently logs errors rather than raising so that the episode update
	itself is not affected by task dispatch failures.

	Args:
		episode: Episode that just became complete/published
	"""
	import logging
	logger = logging.getLogger(__name__)

	try:
		from ..tasks.rss_generation import generate_rss_feed_task
		generate_rss_feed_task.delay(
			str(episode.project_id),
			str(episode.tenant_id),
		)
		logger.info(
			f"Triggered RSS regeneration for project {episode.project_id} "
			f"(episode {episode.id} completed)"
		)
	except Exception as exc:
		logger.warning(
			f"Failed to trigger RSS regeneration for project {episode.project_id}: {exc}"
		)


async def delete_episode(
	db: AsyncSession,
	episode: Episode
) -> None:
	"""
	Hard delete episode.

	Unlike projects, episodes use hard delete (no soft delete).
	Cascade deletes related content sources.

	Args:
		db: Database session
		episode: Episode instance to delete
	"""
	await db.delete(episode)
	await db.commit()


async def update_generation_status(
	db: AsyncSession,
	episode: Episode,
	new_status: str,
	progress_data: Optional[dict] = None
) -> Episode:
	"""
	Update episode generation status.

	Optionally update generation_progress JSONB.
	Useful for tracking generation workflow state.

	Args:
		db: Database session
		episode: Episode instance
		new_status: New generation status (draft, queued, processing, completed, failed)
		progress_data: Optional progress tracking data

	Returns:
		Updated Episode instance
	"""
	episode.generation_status = new_status
	if progress_data:
		episode.generation_progress = progress_data

	await db.commit()
	return episode
