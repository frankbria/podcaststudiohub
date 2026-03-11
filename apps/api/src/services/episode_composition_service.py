"""
Episode composition service layer for business logic.

Provides operations for creating/updating composition timelines, validating
layouts, triggering render tasks, and tracking render status. Tenant isolation
is enforced via RLS policies at the database level.
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.episode import Episode
from ..models.episode_composition import EpisodeComposition
from ..models.audio_snippet import AudioSnippet
from ..schemas.episode_composition import (
	CompositionCreate,
	CompositionValidateResponse,
	RenderResponse,
	RenderStatusResponse,
)


async def get_episode_or_404(db: AsyncSession, episode_id: UUID) -> Episode:
	"""
	Retrieve an episode by ID or raise 404.

	RLS ensures only episodes in the current tenant are accessible.

	Args:
		db: Database session
		episode_id: UUID of the episode

	Returns:
		Episode instance

	Raises:
		HTTPException: 404 if episode not found or belongs to different tenant
	"""
	result = await db.execute(select(Episode).where(Episode.id == episode_id))
	episode = result.scalar_one_or_none()
	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)
	return episode


async def get_or_create_composition(
	db: AsyncSession,
	episode_id: UUID,
	tenant_id: UUID,
) -> EpisodeComposition:
	"""
	Get an existing composition for an episode or create a blank one.

	Args:
		db: Database session
		episode_id: UUID of the episode
		tenant_id: Tenant ID for new composition

	Returns:
		Existing or newly created EpisodeComposition
	"""
	result = await db.execute(
		select(EpisodeComposition).where(EpisodeComposition.episode_id == episode_id)
	)
	composition = result.scalar_one_or_none()

	if composition is None:
		composition = EpisodeComposition(
			episode_id=episode_id,
			tenant_id=tenant_id,
			timeline=[],
			composition_status='draft',
			render_status='draft',
		)
		db.add(composition)
		await db.commit()

	return composition


async def upsert_composition(
	db: AsyncSession,
	episode_id: UUID,
	tenant_id: UUID,
	composition_data: CompositionCreate,
) -> EpisodeComposition:
	"""
	Create or update the composition timeline for an episode.

	Validates that all non-generated snippet references exist and belong
	to the current tenant before saving.

	Args:
		db: Database session
		episode_id: UUID of the episode
		tenant_id: Tenant ID
		composition_data: New timeline and optional layout_id

	Returns:
		Updated EpisodeComposition instance

	Raises:
		HTTPException: 422 if any referenced snippet is not found in tenant
	"""
	# Validate snippet references
	await _validate_snippet_references(
		db=db,
		timeline=composition_data.timeline,
		tenant_id=tenant_id,
	)

	composition = await get_or_create_composition(
		db=db,
		episode_id=episode_id,
		tenant_id=tenant_id,
	)

	composition.timeline = [seg.model_dump(mode="json") for seg in composition_data.timeline]
	composition.layout_id = composition_data.layout_id
	composition.composition_status = 'draft'
	composition.render_status = 'draft'
	composition.render_error = None

	await db.commit()
	return composition


async def _validate_snippet_references(
	db: AsyncSession,
	timeline: list,
	tenant_id: UUID,
) -> None:
	"""
	Verify all snippet_id references in the timeline exist in the tenant.

	Args:
		db: Database session
		timeline: List of TimelineSegment objects
		tenant_id: Tenant ID to check ownership

	Raises:
		HTTPException: 422 if any snippet is not found or belongs to a different tenant
	"""
	for segment in timeline:
		if segment.type == "generated":
			continue
		if segment.snippet_id is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=f"snippet_id is required for segment type '{segment.type}'"
			)
		result = await db.execute(
			select(AudioSnippet).where(
				AudioSnippet.id == segment.snippet_id,
				AudioSnippet.tenant_id == tenant_id,
			)
		)
		if result.scalar_one_or_none() is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=f"Snippet '{segment.snippet_id}' not found in your tenant"
			)


async def validate_composition(
	db: AsyncSession,
	composition: EpisodeComposition,
	tenant_id: UUID,
) -> CompositionValidateResponse:
	"""
	Validate a composition timeline and return analysis results.

	Checks snippet availability, detects timeline gaps, and computes
	estimated total duration.

	Args:
		db: Database session
		composition: EpisodeComposition instance to validate
		tenant_id: Tenant ID for snippet lookup

	Returns:
		CompositionValidateResponse with validity, duration, gaps, and warnings
	"""
	errors: list[str] = []
	warnings: list[str] = []
	gaps: list[dict] = []
	total_duration = 0.0

	timeline = composition.timeline or []

	if not timeline:
		errors.append("Composition timeline is empty")
		return CompositionValidateResponse(
			valid=False,
			total_duration_seconds=0.0,
			gaps=[],
			warnings=[],
			errors=errors,
		)

	has_generated = any(seg.get("type") == "generated" for seg in timeline)
	if not has_generated:
		warnings.append("No 'generated' segment found; episode main audio will not be included")

	# Check snippet availability and accumulate duration
	sorted_segments = sorted(timeline, key=lambda s: s.get("position_seconds", 0.0))
	last_end = 0.0

	for seg in sorted_segments:
		seg_type = seg.get("type")
		snippet_id = seg.get("snippet_id")
		pos = seg.get("position_seconds", 0.0)

		duration = 0.0
		if seg_type == "generated":
			duration = 0.0  # Unknown until generation completes
		elif snippet_id:
			result = await db.execute(
				select(AudioSnippet).where(
					AudioSnippet.id == snippet_id,
					AudioSnippet.tenant_id == tenant_id,
				)
			)
			snippet = result.scalar_one_or_none()
			if snippet is None:
				errors.append(f"Snippet '{snippet_id}' not found in your tenant")
			else:
				duration = float(snippet.duration_seconds or 0.0)

		# Detect gaps (silence periods between segments)
		if pos > last_end and last_end > 0:
			gap_duration = pos - last_end
			if gap_duration > 1.0:
				gaps.append({
					"start_seconds": last_end,
					"end_seconds": pos,
					"duration_seconds": gap_duration,
				})
				warnings.append(
					f"Gap of {gap_duration:.1f}s between segments at {last_end:.1f}s and {pos:.1f}s"
				)

		last_end = pos + duration
		total_duration = max(total_duration, last_end)

	return CompositionValidateResponse(
		valid=len(errors) == 0,
		total_duration_seconds=total_duration,
		gaps=gaps,
		warnings=warnings,
		errors=errors,
	)


async def render_composition(
	db: AsyncSession,
	episode: Episode,
	composition: EpisodeComposition,
) -> RenderResponse:
	"""
	Trigger the Celery task to merge audio segments for this composition.

	Updates composition render_status to 'composing' and returns the task ID.

	Args:
		db: Database session
		episode: Episode instance
		composition: EpisodeComposition instance to render

	Returns:
		RenderResponse with task_id for progress tracking

	Raises:
		HTTPException: 422 if timeline is empty
	"""
	if not composition.timeline:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="Cannot render: composition timeline is empty"
		)

	import tempfile
	import os

	from ..worker import celery_app

	# Determine output path
	output_dir = tempfile.gettempdir()
	output_path = os.path.join(output_dir, f"episode_{episode.id}_composition.mp3")

	# Dispatch Celery task
	task = celery_app.send_task(
		"merge_audio_snippets",
		args=[
			str(episode.id),
			str(composition.id),
			composition.timeline,
			output_path,
		],
	)

	# Mark composition as composing
	composition.render_status = 'composing'
	composition.render_error = None
	await db.commit()

	return RenderResponse(
		task_id=task.id,
		status="queued",
		episode_id=episode.id,
		composition_id=composition.id,
	)


async def get_render_status(
	composition: EpisodeComposition,
	task_id: Optional[str] = None,
) -> RenderStatusResponse:
	"""
	Get the current render status for a composition.

	Checks Celery task status if task_id provided, otherwise returns
	the persisted render_status from the composition record.

	Args:
		composition: EpisodeComposition instance
		task_id: Optional Celery task ID for real-time progress

	Returns:
		RenderStatusResponse with current status and progress
	"""
	if task_id:
		try:
			from ..worker import celery_app
			from celery.result import AsyncResult

			result = AsyncResult(task_id, app=celery_app)
			state = result.state

			if state == "PENDING":
				return RenderStatusResponse(status="queued", progress=0)
			elif state == "PROGRESS":
				meta = result.info or {}
				return RenderStatusResponse(
					status="processing",
					progress=meta.get("progress", 0),
				)
			elif state == "SUCCESS":
				task_result = result.result or {}
				return RenderStatusResponse(
					status="complete",
					progress=100,
					result=task_result,
				)
			elif state in ("FAILURE", "REVOKED"):
				return RenderStatusResponse(
					status="failed",
					progress=0,
					error=str(result.info),
				)
		except Exception:
			pass

	# Fall back to persisted status
	status_map = {
		'draft': 'queued',
		'composing': 'processing',
		'complete': 'complete',
		'failed': 'failed',
	}
	mapped_status = status_map.get(composition.render_status, composition.render_status)

	return RenderStatusResponse(
		status=mapped_status,
		progress=100 if composition.render_status == 'complete' else 0,
		error=composition.render_error,
	)
