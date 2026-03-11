"""
Episode composition router for RESTful API endpoints.

Provides endpoints for managing the audio composition timeline for episodes:
creating/updating the timeline, validating layout, triggering renders, and
checking render status. All endpoints require authentication and are scoped
to a specific episode (via episode_id path parameter).
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.episode_composition import (
	CompositionCreate,
	CompositionResponse,
	CompositionValidateResponse,
	RenderResponse,
	RenderStatusResponse,
)
from ..services.episode_composition_service import (
	get_episode_or_404,
	get_or_create_composition,
	upsert_composition,
	validate_composition,
	render_composition,
	get_render_status,
)

router = APIRouter(
	prefix="/episodes/{episode_id}/composition",
	tags=["episode-compositions"],
)


@router.post(
	"",
	response_model=CompositionResponse,
	status_code=status.HTTP_200_OK,
	summary="Create or update episode composition timeline",
)
async def upsert_episode_composition(
	episode_id: UUID,
	composition_data: CompositionCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create or update the composition timeline for an episode.

	Idempotent: calling this multiple times replaces the timeline.
	Validates all non-generated segment snippet references before saving.
	Resets render_status to 'draft' on update.

	Args:
		episode_id: UUID of the episode
		composition_data: Timeline segments and optional layout_id
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated composition with timeline and status fields

	Raises:
		HTTPException: 404 if episode not found
		HTTPException: 422 if snippet references are invalid
	"""
	await get_episode_or_404(db=db, episode_id=episode_id)

	composition = await upsert_composition(
		db=db,
		episode_id=episode_id,
		tenant_id=current_user.tenant_id,
		composition_data=composition_data,
	)
	return composition


@router.get(
	"",
	response_model=CompositionResponse,
	summary="Get episode composition",
)
async def get_episode_composition(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get the current composition layout for an episode.

	Returns the existing composition if present. Creates and returns a blank
	draft composition if one does not yet exist.

	Args:
		episode_id: UUID of the episode
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Composition with timeline, render status, and composed audio info

	Raises:
		HTTPException: 404 if episode not found
	"""
	await get_episode_or_404(db=db, episode_id=episode_id)

	composition = await get_or_create_composition(
		db=db,
		episode_id=episode_id,
		tenant_id=current_user.tenant_id,
	)
	return composition


@router.post(
	"/validate",
	response_model=CompositionValidateResponse,
	summary="Validate episode composition layout",
)
async def validate_episode_composition(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Validate the current composition layout without triggering a render.

	Checks snippet availability, detects timeline gaps, and estimates total
	duration. Useful for UI previews before committing to a full render.

	Args:
		episode_id: UUID of the episode
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Validation result with validity, duration, gaps, warnings, and errors

	Raises:
		HTTPException: 404 if episode or composition not found
	"""
	await get_episode_or_404(db=db, episode_id=episode_id)

	composition = await get_or_create_composition(
		db=db,
		episode_id=episode_id,
		tenant_id=current_user.tenant_id,
	)

	return await validate_composition(
		db=db,
		composition=composition,
		tenant_id=current_user.tenant_id,
	)


@router.post(
	"/render",
	response_model=RenderResponse,
	status_code=status.HTTP_202_ACCEPTED,
	summary="Trigger episode composition render",
)
async def render_episode_composition(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Start an asynchronous render task to merge audio segments.

	Dispatches a Celery task that downloads snippet audio from S3, merges
	segments with fade/normalization, and uploads the composed audio.
	Returns a task ID that can be polled via the /status endpoint.

	Args:
		episode_id: UUID of the episode
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Task ID and initial status for progress tracking

	Raises:
		HTTPException: 404 if episode or composition not found
		HTTPException: 422 if composition timeline is empty
	"""
	episode = await get_episode_or_404(db=db, episode_id=episode_id)

	composition = await get_or_create_composition(
		db=db,
		episode_id=episode_id,
		tenant_id=current_user.tenant_id,
	)

	return await render_composition(
		db=db,
		episode=episode,
		composition=composition,
	)


@router.get(
	"/status",
	response_model=RenderStatusResponse,
	summary="Get composition render status",
)
async def get_composition_render_status(
	episode_id: UUID,
	task_id: Optional[str] = Query(None, description="Celery task ID for real-time progress"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get the current render status for an episode composition.

	If a task_id is provided, queries Celery for real-time progress.
	Otherwise falls back to the persisted render_status on the composition.

	Args:
		episode_id: UUID of the episode
		task_id: Optional Celery task ID for real-time progress
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Current status, progress percentage, and optional result/error

	Raises:
		HTTPException: 404 if episode not found
	"""
	await get_episode_or_404(db=db, episode_id=episode_id)

	composition = await get_or_create_composition(
		db=db,
		episode_id=episode_id,
		tenant_id=current_user.tenant_id,
	)

	return await get_render_status(
		composition=composition,
		task_id=task_id,
	)
