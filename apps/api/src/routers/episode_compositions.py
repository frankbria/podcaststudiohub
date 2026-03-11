"""
Episode composition router for RESTful API endpoints.

Provides layout management and audio composition rendering for podcast episodes.
All endpoints require authentication and enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.episode_composition import (
	CompositionLayoutCreate,
	CompositionResponse,
	CompositionStatusResponse,
	RenderResponse,
	ValidationResult,
)
from ..services.episode_composition_service import (
	create_or_update_layout,
	get_composition,
	get_composition_status,
	render_composition,
	validate_layout,
)

router = APIRouter(prefix="/episodes", tags=["episode-compositions"])


@router.post(
	"/{episode_id}/composition",
	response_model=CompositionResponse,
	status_code=status.HTTP_200_OK,
)
async def create_or_update_composition(
	episode_id: UUID,
	layout_data: CompositionLayoutCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create or update the composition layout for an episode.

	Accepts a timeline of audio segments (intro, generated content, outro, etc.)
	and saves the layout. Validates all referenced snippet IDs exist.

	Args:
		episode_id: UUID of the episode
		layout_data: Timeline segments defining composition order
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created or updated EpisodeComposition

	Raises:
		HTTPException: 404 if episode not found, 422 if snippet IDs invalid
	"""
	composition = await create_or_update_layout(
		db=db,
		episode_id=episode_id,
		layout_data=layout_data,
		tenant_id=current_user.tenant_id,
	)
	return composition


@router.get(
	"/{episode_id}/composition",
	response_model=CompositionResponse,
)
async def get_episode_composition(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get the current composition layout for an episode.

	Args:
		episode_id: UUID of the episode
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		EpisodeComposition with timeline and render status

	Raises:
		HTTPException: 404 if no composition exists for this episode
	"""
	composition = await get_composition(db=db, episode_id=episode_id)

	if composition is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="No composition found for this episode"
		)

	return composition


@router.post(
	"/{episode_id}/composition/validate",
	response_model=ValidationResult,
)
async def validate_composition_layout(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Validate the current composition layout without saving.

	Checks for timeline gaps, overlapping segments, and missing snippets.

	Args:
		episode_id: UUID of the episode
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		ValidationResult with gaps, warnings, and validity flag

	Raises:
		HTTPException: 404 if no composition exists for this episode
	"""
	composition = await get_composition(db=db, episode_id=episode_id)

	if composition is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="No composition found for this episode"
		)

	result = await validate_layout(db=db, composition=composition)
	return result


@router.post(
	"/{episode_id}/composition/render",
	response_model=RenderResponse,
	status_code=status.HTTP_202_ACCEPTED,
)
async def render_episode_composition(
	episode_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Trigger audio composition rendering for an episode.

	Starts a Celery task to merge audio snippets according to the saved timeline.
	Returns a task ID for progress tracking.

	Args:
		episode_id: UUID of the episode
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		RenderResponse with task_id and queued status

	Raises:
		HTTPException: 404 if no composition exists, 409 if already rendering
	"""
	composition = await get_composition(db=db, episode_id=episode_id)

	if composition is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="No composition found for this episode"
		)

	if composition.render_status == "composing":
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="Composition is already being rendered"
		)

	result = await render_composition(
		db=db,
		episode_id=episode_id,
		composition=composition,
	)
	return RenderResponse(**result)


@router.get(
	"/{episode_id}/composition/status",
	response_model=CompositionStatusResponse,
)
async def get_render_status(
	episode_id: UUID,
	task_id: str = Query(..., description="Celery task ID from render response"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get the progress of a composition render task.

	Args:
		episode_id: UUID of the episode (for authorization)
		task_id: Celery task ID returned by the render endpoint
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		CompositionStatusResponse with status, progress percentage, and ETA

	Raises:
		HTTPException: 404 if no composition exists for this episode
	"""
	# Verify the episode has a composition (authorization check)
	composition = await get_composition(db=db, episode_id=episode_id)

	if composition is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="No composition found for this episode"
		)

	status_info = await get_composition_status(task_id=task_id)
	return CompositionStatusResponse(**status_info)
