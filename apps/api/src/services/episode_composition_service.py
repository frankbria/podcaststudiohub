"""
Episode composition service layer for business logic.

Provides operations for managing episode audio composition layouts,
validating timelines, triggering render tasks, and tracking status.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audio_snippet import AudioSnippet
from ..models.episode import Episode
from ..models.episode_composition import EpisodeComposition
from ..schemas.episode_composition import (
	CompositionLayoutCreate,
	GapInfo,
	ValidationResult,
)

logger = logging.getLogger(__name__)


async def get_composition(
	db: AsyncSession,
	episode_id: UUID,
) -> Optional[EpisodeComposition]:
	"""
	Get composition for an episode.

	Args:
		db: Database session
		episode_id: UUID of the episode

	Returns:
		EpisodeComposition instance or None
	"""
	result = await db.execute(
		select(EpisodeComposition).where(
			EpisodeComposition.episode_id == episode_id
		)
	)
	return result.scalar_one_or_none()


async def create_or_update_layout(
	db: AsyncSession,
	episode_id: UUID,
	layout_data: CompositionLayoutCreate,
	tenant_id: UUID,
) -> EpisodeComposition:
	"""
	Create or update the composition layout for an episode.

	Validates that all referenced snippet_ids exist. Sets render_status to None
	(not yet triggered) and composition_status to 'draft'.

	Args:
		db: Database session
		episode_id: UUID of episode
		layout_data: Composition layout with timeline segments
		tenant_id: Tenant ID for isolation

	Returns:
		Created or updated EpisodeComposition instance

	Raises:
		HTTPException: 404 if episode not found, 422 if snippet not found
	"""
	# Verify episode exists
	episode = await db.get(Episode, episode_id)
	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)

	# Validate all snippet_ids exist
	snippet_ids = [
		seg.snippet_id
		for seg in layout_data.timeline
		if seg.snippet_id is not None
	]
	if snippet_ids:
		result = await db.execute(
			select(AudioSnippet).where(AudioSnippet.id.in_(snippet_ids))
		)
		found_snippets = result.scalars().all()
		found_ids = {s.id for s in found_snippets}
		missing_ids = set(snippet_ids) - found_ids
		if missing_ids:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=f"Audio snippets not found: {[str(i) for i in missing_ids]}"
			)

	# Serialize timeline to dict list
	timeline_data = [seg.model_dump(mode="json") for seg in layout_data.timeline]

	# Check if composition already exists
	existing = await get_composition(db, episode_id)

	if existing is not None:
		existing.timeline = timeline_data
		existing.composition_status = "draft"
		existing.render_status = None
		existing.render_error = None
		await db.commit()
		return existing

	# Create new composition
	composition = EpisodeComposition(
		episode_id=episode_id,
		tenant_id=tenant_id,
		timeline=timeline_data,
		composition_status="draft",
		render_status=None,
	)
	db.add(composition)
	await db.commit()
	return composition


async def validate_layout(
	db: AsyncSession,
	composition: EpisodeComposition,
) -> ValidationResult:
	"""
	Validate the composition layout for gaps and snippet availability.

	Args:
		db: Database session
		composition: EpisodeComposition to validate

	Returns:
		ValidationResult with gaps, warnings, and validity flag
	"""
	warnings: List[str] = []
	gaps: List[GapInfo] = []

	timeline = composition.timeline or []
	if not timeline:
		return ValidationResult(
			valid=False,
			total_duration=0.0,
			gaps=[],
			warnings=["Timeline is empty"]
		)

	# Collect snippet_ids for validation
	snippet_ids = [
		UUID(seg["snippet_id"])
		for seg in timeline
		if seg.get("snippet_id")
	]
	if snippet_ids:
		result = await db.execute(
			select(AudioSnippet).where(AudioSnippet.id.in_(snippet_ids))
		)
		found_ids = {s.id for s in result.scalars().all()}
		missing_ids = set(snippet_ids) - found_ids
		if missing_ids:
			warnings.append(
				f"Audio snippets no longer exist: {[str(i) for i in missing_ids]}"
			)

	# Sort segments by position and check for gaps
	sorted_segments = sorted(timeline, key=lambda s: s.get("position_seconds", 0))
	current_pos = 0.0
	total_duration = 0.0

	for seg in sorted_segments:
		pos = float(seg.get("position_seconds", 0))
		if pos > current_pos + 0.5:  # gap greater than 0.5s
			gaps.append(GapInfo(
				start_seconds=current_pos,
				end_seconds=pos,
				duration_seconds=pos - current_pos,
			))
		# Estimate duration from snippet (if available)
		snippet_id = seg.get("snippet_id")
		seg_duration = 0.0
		if snippet_id:
			snippet = await db.get(AudioSnippet, UUID(snippet_id))
			if snippet and snippet.duration_seconds:
				seg_duration = float(snippet.duration_seconds)
		current_pos = pos + seg_duration
		total_duration = max(total_duration, current_pos)

	if gaps:
		warnings.append(f"Timeline has {len(gaps)} silence gap(s)")

	# Check for overlapping segments
	for i in range(len(sorted_segments) - 1):
		seg_a = sorted_segments[i]
		seg_b = sorted_segments[i + 1]
		pos_a = float(seg_a.get("position_seconds", 0))
		pos_b = float(seg_b.get("position_seconds", 0))
		if pos_a == pos_b:
			warnings.append(
				f"Two segments start at the same position ({pos_a}s)"
			)

	valid = len(warnings) == 0 or all("no longer exist" not in w for w in warnings)

	return ValidationResult(
		valid=valid,
		total_duration=total_duration,
		gaps=gaps,
		warnings=warnings,
	)


async def render_composition(
	db: AsyncSession,
	episode_id: UUID,
	composition: EpisodeComposition,
) -> Dict[str, Any]:
	"""
	Trigger the audio composition Celery task.

	Updates composition render_status to 'pending' and queues the task.

	Args:
		db: Database session
		episode_id: UUID of episode
		composition: EpisodeComposition to render

	Returns:
		Dict with task_id, status, episode_id, composition_id
	"""
	from ..tasks.audio_composition import merge_audio_snippets_task

	# Update render status to pending
	composition.render_status = "pending"
	composition.render_error = None
	await db.commit()

	# Build output path
	output_path = f"/tmp/composition_{composition.id}.mp3"

	# Trigger Celery task
	task = merge_audio_snippets_task.apply_async(
		kwargs={
			"episode_id": str(episode_id),
			"composition_id": str(composition.id),
			"timeline": composition.timeline,
			"output_path": output_path,
		}
	)

	return {
		"task_id": task.id,
		"status": "queued",
		"episode_id": str(episode_id),
		"composition_id": str(composition.id),
	}


async def get_composition_status(task_id: str) -> Dict[str, Any]:
	"""
	Get the status of a composition Celery task.

	Args:
		task_id: Celery task ID

	Returns:
		Dict with status, progress, eta_seconds, error, result
	"""
	from ..worker import celery_app

	async_result = celery_app.AsyncResult(task_id)
	state = async_result.state

	if state == "PENDING":
		return {
			"task_id": task_id,
			"status": "pending",
			"progress": 0,
			"eta_seconds": None,
			"error": None,
			"result": None,
		}
	elif state == "STARTED":
		return {
			"task_id": task_id,
			"status": "composing",
			"progress": 0,
			"eta_seconds": None,
			"error": None,
			"result": None,
		}
	elif state == "PROGRESS":
		meta = async_result.info or {}
		return {
			"task_id": task_id,
			"status": "composing",
			"progress": meta.get("progress", 0),
			"eta_seconds": meta.get("eta_seconds"),
			"error": None,
			"result": None,
		}
	elif state == "SUCCESS":
		result = async_result.result or {}
		return {
			"task_id": task_id,
			"status": "complete",
			"progress": 100,
			"eta_seconds": None,
			"error": None,
			"result": result,
		}
	elif state == "FAILURE":
		error = str(async_result.info) if async_result.info else "Unknown error"
		return {
			"task_id": task_id,
			"status": "failed",
			"progress": 0,
			"eta_seconds": None,
			"error": error,
			"result": None,
		}
	else:
		return {
			"task_id": task_id,
			"status": state.lower(),
			"progress": 0,
			"eta_seconds": None,
			"error": None,
			"result": None,
		}
