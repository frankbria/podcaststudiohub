"""
Episode service layer for business logic.

Provides CRUD operations for episodes with project validation, pagination,
status filtering, and generation status management. RLS ensures tenant isolation.
"""

import logging

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from uuid import UUID
from typing import Optional, List
from fastapi import HTTPException, status

from ..models import Episode, Project
from ..models.episode_composition import EpisodeComposition
from ..models.storage_deletion_outbox import StorageDeletionOutbox
from ..schemas.episode import EpisodeCreate, EpisodeUpdate, BatchEpisodeCreate
from ..tasks.maintenance import drain_storage_deletion_outbox
from ..utils.datetime_utils import to_naive_utc

logger = logging.getLogger(__name__)

# Valid sort fields and orders for episode listing
VALID_SORT_FIELDS = {"episode_number", "created_at", "duration_seconds"}
VALID_SORT_ORDERS = {"asc", "desc"}

# Fields an end user may set through the public update endpoint. Everything else
# (generation_status, generation_progress, s3_key/s3_url, duration_seconds,
# file_size_bytes, file_path, transcript_path, task_*) is system-managed and is
# written only by the generation pipeline via set_episode_system_fields(). This
# allowlist is the source of truth: a system field re-added to EpisodeUpdate stays
# unwritable until it is deliberately added here.
EPISODE_USER_EDITABLE_FIELDS = {
	"episode_number",
	"episode_metadata",
	"tts_config_id",
	"template_id",
}


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
	status_filter: Optional[str] = None,
	search: Optional[str] = None,
	date_from: Optional[datetime] = None,
	date_to: Optional[datetime] = None,
	tags: Optional[List[str]] = None,
	tts_config_id: Optional[UUID] = None,
	min_duration: Optional[float] = None,
	max_duration: Optional[float] = None,
	sort_by: str = "episode_number",
	sort_order: str = "asc"
) -> tuple[list[Episode], int]:
	"""
	Get paginated list of episodes with optional search and filtering.

	Optionally filter by project_id, generation_status, text search,
	date range, tags, TTS config, and duration range.
	RLS automatically filters by tenant.

	Args:
		db: Database session
		project_id: Optional project ID to filter by
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return
		status_filter: Optional generation status to filter by
		search: Optional text to search in title and description (case-insensitive)
		date_from: Optional start of date range filter on created_at
		date_to: Optional end of date range filter on created_at
		tags: Optional list of tags (all must match, AND logic)
		tts_config_id: Optional TTS configuration UUID to filter by
		min_duration: Optional minimum duration in seconds
		max_duration: Optional maximum duration in seconds
		sort_by: Field to sort by (episode_number, created_at, duration_seconds)
		sort_order: Sort direction (asc, desc)

	Returns:
		Tuple of (episodes list, total count)
	"""
	# Build base query
	query = select(Episode)

	if project_id:
		query = query.where(Episode.project_id == project_id)

	if status_filter:
		query = query.where(Episode.generation_status == status_filter)

	# Full-text search on title and description (case-insensitive)
	if search and search.strip():
		search_term = f"%{search.strip()}%"
		query = query.where(
			or_(
				Episode.episode_metadata['title'].astext.ilike(search_term),
				Episode.episode_metadata['description'].astext.ilike(search_term)
			)
		)

	# Date range filter — created_at is offset-naive UTC, so normalize inputs
	if date_from is not None:
		query = query.where(Episode.created_at >= to_naive_utc(date_from))

	if date_to is not None:
		query = query.where(Episode.created_at <= to_naive_utc(date_to))

	# Tag filter — each tag must be present in episode_metadata.tags array (AND logic)
	# Uses PostgreSQL JSONB @> operator: episode_metadata->'tags' @> '["tag"]'::jsonb
	if tags:
		for tag in tags:
			query = query.where(
				Episode.episode_metadata['tags'].op('@>')(cast([tag], JSONB))
			)

	# TTS config filter
	if tts_config_id is not None:
		query = query.where(Episode.tts_config_id == tts_config_id)

	# Duration range filter
	if min_duration is not None:
		query = query.where(Episode.duration_seconds >= min_duration)

	if max_duration is not None:
		query = query.where(Episode.duration_seconds <= max_duration)

	# Get total count (before pagination)
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar() or 0  # guard None -> total_pages TypeError (issue #337)

	# Apply sort order
	sort_column = {
		"episode_number": Episode.episode_number,
		"created_at": Episode.created_at,
		"duration_seconds": Episode.duration_seconds,
	}.get(sort_by, Episode.episode_number)

	if sort_order == "desc":
		query = query.order_by(sort_column.desc())
	else:
		query = query.order_by(sort_column.asc())

	# Apply pagination
	query = query.offset(skip).limit(limit)
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

	Args:
		db: Database session
		episode: Existing episode instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated Episode instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)
	for field, value in update_dict.items():
		if field not in EPISODE_USER_EDITABLE_FIELDS:
			# Never mass-assign system-managed fields, even if a future schema
			# change re-adds one to EpisodeUpdate.
			continue
		if field == "episode_metadata":
			if value is None:
				continue  # can't null a NOT NULL JSONB column; treat as no-op
			# Shallow-merge into existing JSONB so a partial update (e.g. title
			# only, from the edit dialog) doesn't drop other keys like
			# description/format/explicit/tags (issue #337).
			value = {**(episode.episode_metadata or {}), **value}
		setattr(episode, field, value)

	await db.commit()
	return episode


async def set_episode_system_fields(
	db: AsyncSession,
	episode: Episode,
	**fields,
) -> Episode:
	"""Write pipeline-managed (system) episode fields directly.

	For internal use by the generation pipeline only (e.g. transcript_path,
	generation_progress, s3_key). This intentionally bypasses the
	EPISODE_USER_EDITABLE_FIELDS allowlist that guards update_episode, so it must
	never be reachable from a request handler with user-controlled field names.

	Args:
		db: Database session
		episode: Existing episode instance
		**fields: Episode column names mapped to their new values

	Returns:
		Updated Episode instance
	"""
	for field, value in fields.items():
		setattr(episode, field, value)

	await db.commit()
	return episode


async def delete_episode(
	db: AsyncSession,
	episode: Episode
) -> None:
	"""
	Hard delete episode.

	Unlike projects, episodes use hard delete (no soft delete).
	Cascade deletes related content sources.

	Queues the episode's S3 audio object, its EpisodeComposition's composed S3
	audio object (if any), and local file artifacts (episode audio, transcript,
	composed audio) onto the durable storage_deletion_outbox in the same
	transaction as the row delete, instead of deleting from storage inline
	(issue #366). A commit failure here therefore leaves storage untouched —
	nothing is deleted from S3/disk until the row delete itself is durable. The
	GC worker (drain_storage_deletion_outbox) performs the actual deletion,
	retrying until it succeeds; a best-effort post-commit trigger below makes
	that happen promptly instead of waiting for the next beat tick.

	Args:
		db: Database session
		episode: Episode instance to delete
	"""
	composition_result = await db.execute(
		select(EpisodeComposition).where(EpisodeComposition.episode_id == episode.id)
	)
	composition = composition_result.scalar_one_or_none()

	s3_keys = [
		key for key in (
			episode.s3_key,
			composition.composed_s3_key if composition else None,
		) if key
	]
	for key in s3_keys:
		db.add(StorageDeletionOutbox(tenant_id=episode.tenant_id, s3_key=key))

	local_paths = [
		path for path in (
			episode.file_path,
			episode.transcript_path,
			composition.composed_file_path if composition else None,
		) if path
	]
	for path in local_paths:
		db.add(StorageDeletionOutbox(tenant_id=episode.tenant_id, file_path=path))

	await db.delete(episode)
	await db.commit()

	if s3_keys or local_paths:
		try:
			drain_storage_deletion_outbox.delay()
		except Exception:
			logger.warning(f"Failed to trigger storage deletion drain for episode {episode.id}")


async def batch_create_episodes(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	batch_data: BatchEpisodeCreate
) -> dict:
	"""
	Create multiple episodes in a single batch operation.

	Processes each episode individually, collecting successes and failures.
	Partial success is supported: valid episodes are created even when some fail.

	Args:
		db: Database session
		user_id: ID of user creating the episodes
		tenant_id: Tenant ID for isolation
		batch_data: Batch creation data with list of episode configs

	Returns:
		Dict with batch_id, status, counts, and per-episode results
	"""
	import uuid as _uuid

	batch_id = str(_uuid.uuid4())
	results = []
	created_count = 0
	failed_count = 0

	for index, episode_data in enumerate(batch_data.episodes):
		try:
			episode = await create_episode(
				db=db,
				user_id=user_id,
				tenant_id=tenant_id,
				episode_data=episode_data
			)
			results.append({
				"index": index,
				"status": "created",
				"episode": episode,
				"error": None,
			})
			created_count += 1
		except HTTPException as exc:
			results.append({
				"index": index,
				"status": "failed",
				"episode": None,
				"error": exc.detail,
			})
			failed_count += 1

	overall_status = "complete" if failed_count == 0 else "partial"

	return {
		"batch_id": batch_id,
		"status": overall_status,
		"total_episodes": len(batch_data.episodes),
		"created_count": created_count,
		"failed_count": failed_count,
		"results": results,
	}


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
