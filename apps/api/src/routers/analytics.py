"""
Analytics router: event tracking and usage metrics endpoints.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..models.episode import Episode
from ..models.project import Project
from ..schemas.analytics import (
	AnalyticsEventResponse,
	EpisodeAnalyticsResponse,
	ProjectAnalyticsResponse,
	TrackEventRequest,
)
from ..services import analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# POST /analytics/events — public event tracking
# ---------------------------------------------------------------------------


@router.post(
	"/analytics/events",
	response_model=AnalyticsEventResponse,
	status_code=status.HTTP_201_CREATED,
)
async def track_event(
	body: TrackEventRequest,
	request: Request,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Track a user engagement event (play, download, share, stream)."""
	# Validate episode exists and belongs to user's tenant
	if body.episode_id is not None:
		ep_result = await db.execute(
			select(Episode).where(Episode.id == body.episode_id)
		)
		episode = ep_result.scalar_one_or_none()
		if episode is None:
			raise HTTPException(status_code=404, detail="Episode not found")

	# Validate project exists and belongs to user's tenant
	if body.project_id is not None:
		proj_result = await db.execute(
			select(Project).where(Project.id == body.project_id)
		)
		project = proj_result.scalar_one_or_none()
		if project is None:
			raise HTTPException(status_code=404, detail="Project not found")

	client_ip = request.headers.get("X-Forwarded-For") or request.client.host if request.client else None
	user_agent = request.headers.get("User-Agent")
	referer = request.headers.get("Referer")
	# Country from the edge/CDN (Cloudflare CF-IPCountry, generic X-Country
	# fallback); normalized + sentinel-filtered in build_event_payload (#325).
	country = request.headers.get("CF-IPCountry") or request.headers.get("X-Country")

	# Build the event payload in-process (id + created_at minted here) and queue
	# the insert so the per-event commit is off the request path (issue #322).
	# ValueError → 422 for an invalid event_type (Pydantic already constrains the
	# request, but keep the contract explicit).
	try:
		payload = analytics_service.build_event_payload(
			tenant_id=current_user.tenant_id,
			event_type=body.event_type,
			episode_id=body.episode_id,
			project_id=body.project_id,
			user_agent=user_agent,
			referer=referer,
			ip_address=client_ip,
			country=country,
			event_metadata=body.metadata,
		)
	except ValueError as exc:
		raise HTTPException(status_code=422, detail=str(exc))

	try:
		from ..tasks.analytics import track_analytics_event_task
		track_analytics_event_task.delay(payload=payload)
	except Exception as e:
		# Broker unavailable — analytics are fire-and-forget; log and still 201.
		logger.warning(f"Could not queue analytics event {payload['id']}: {e}")

	return AnalyticsEventResponse(
		id=payload["id"],
		event_type=payload["event_type"],
		episode_id=payload["episode_id"],
		project_id=payload["project_id"],
		event_metadata=payload["event_metadata"],
		created_at=payload["created_at"],
	)


# ---------------------------------------------------------------------------
# GET /analytics/episodes/{episode_id} — episode analytics (protected)
# ---------------------------------------------------------------------------


@router.get(
	"/analytics/episodes/{episode_id}",
	response_model=EpisodeAnalyticsResponse,
)
async def get_episode_analytics(
	episode_id: UUID,
	date_from: Optional[datetime] = None,
	date_to: Optional[datetime] = None,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get aggregated analytics for an episode."""
	ep_result = await db.execute(
		select(Episode).where(Episode.id == episode_id)
	)
	episode = ep_result.scalar_one_or_none()
	if episode is None:
		raise HTTPException(status_code=404, detail="Episode not found")

	data = await analytics_service.get_episode_analytics(
		db=db,
		episode_id=episode_id,
		date_from=date_from,
		date_to=date_to,
	)
	return data


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/analytics — project analytics (protected)
# ---------------------------------------------------------------------------


@router.get(
	"/projects/{project_id}/analytics",
	response_model=ProjectAnalyticsResponse,
)
async def get_project_analytics(
	project_id: UUID,
	days: int = 30,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get aggregated analytics for a project (default: last 30 days)."""
	proj_result = await db.execute(
		select(Project).where(Project.id == project_id)
	)
	project = proj_result.scalar_one_or_none()
	if project is None:
		raise HTTPException(status_code=404, detail="Project not found")

	data = await analytics_service.get_project_analytics(
		db=db,
		project_id=project_id,
		days=days,
	)
	return data
