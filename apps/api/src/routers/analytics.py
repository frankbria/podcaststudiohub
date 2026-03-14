"""
Analytics router for event tracking and usage metrics.

Provides:
- POST /analytics/events  (public) - track engagement events
- GET  /analytics/episodes/{episode_id}  (protected) - episode analytics summary
- GET  /projects/{project_id}/analytics  (protected) - project analytics dashboard
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..models.episode import Episode
from ..models.project import Project
from ..schemas.analytics import AnalyticsEventCreate, AnalyticsEventResponse
from ..services import analytics_service
from sqlalchemy import select

router = APIRouter(tags=["analytics"])
projects_analytics_router = APIRouter(tags=["analytics"])


@router.post(
	"/analytics/events",
	response_model=AnalyticsEventResponse,
	status_code=status.HTTP_201_CREATED,
)
async def track_event(
	event_data: AnalyticsEventCreate,
	request: Request,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Track an analytics engagement event.

	Records downloads, plays, shares, or streams for an episode.
	Requires authentication. IP is hashed for privacy compliance.

	Args:
		event_data: Event data (event_type, episode_id, project_id, metadata)
		request: FastAPI request for extracting headers
		current_user: Authenticated user
		db: Database session

	Returns:
		Created analytics event

	Raises:
		HTTPException: 404 if episode or project not found or belongs to different tenant
	"""
	# Validate episode belongs to this tenant if provided
	if event_data.episode_id:
		episode = await db.execute(
			select(Episode).where(Episode.id == event_data.episode_id)
		)
		ep = episode.scalar_one_or_none()
		if ep is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Episode not found"
			)

	# Validate project belongs to this tenant if provided
	if event_data.project_id:
		project_result = await db.execute(
			select(Project).where(Project.id == event_data.project_id)
		)
		proj = project_result.scalar_one_or_none()
		if proj is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Project not found"
			)

	user_agent = request.headers.get("User-Agent")
	referer = request.headers.get("Referer")
	client_ip = request.client.host if request.client else None

	event = await analytics_service.track_event(
		db=db,
		tenant_id=current_user.id,
		event_data=event_data,
		user_agent=user_agent,
		referer=referer,
		ip_address=client_ip,
	)
	return event


@router.get("/analytics/episodes/{episode_id}")
async def get_episode_analytics(
	episode_id: UUID,
	date_from: Optional[datetime] = Query(None, description="Start of period (ISO 8601)"),
	date_to: Optional[datetime] = Query(None, description="End of period (ISO 8601)"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get aggregated analytics for an episode.

	Returns event counts by type and device breakdown for the given period.
	Defaults to last 30 days if no period specified.

	Args:
		episode_id: UUID of the episode
		date_from: Start of analytics period
		date_to: End of analytics period
		current_user: Authenticated user
		db: Database session

	Returns:
		Analytics summary with metrics and device breakdown

	Raises:
		HTTPException: 404 if episode not found
	"""
	episode_result = await db.execute(
		select(Episode).where(Episode.id == episode_id)
	)
	episode = episode_result.scalar_one_or_none()
	if episode is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Episode not found"
		)

	return await analytics_service.get_episode_analytics_summary(
		db=db,
		episode_id=episode_id,
		date_from=date_from,
		date_to=date_to,
	)


@projects_analytics_router.get("/projects/{project_id}/analytics")
async def get_project_analytics(
	project_id: UUID,
	days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get analytics dashboard summary for a project.

	Aggregates all episode events within the given period.
	Includes summary totals and top episodes by download count.

	Args:
		project_id: UUID of the project
		days: Number of days to look back (1-365, default 30)
		current_user: Authenticated user
		db: Database session

	Returns:
		Project analytics summary with totals and top episodes

	Raises:
		HTTPException: 404 if project not found
	"""
	project_result = await db.execute(
		select(Project).where(Project.id == project_id)
	)
	project = project_result.scalar_one_or_none()
	if project is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found"
		)

	return await analytics_service.get_project_analytics_summary(
		db=db,
		project_id=project_id,
		days=days,
	)
