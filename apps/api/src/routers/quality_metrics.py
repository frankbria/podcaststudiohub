"""
Quality metrics router for RESTful API endpoints.

Provides endpoints to retrieve calculated quality metrics for episodes and
aggregated quality summaries for projects. All endpoints require authentication
and automatically enforce tenant isolation via RLS.
"""

from datetime import datetime
from typing import Optional, Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import Episode, Project, User
from ..schemas.quality_metrics import (
	EpisodeQualityMetricsResponse,
	ProjectQualityMetricsResponse,
	QualityMetricsData,
	QualityMetricsListResponse,
	QualityScore,
)
from ..services.quality_score_service import QualityScoreService, _rating_from_score

router = APIRouter(prefix="/quality-metrics", tags=["quality-metrics"])

_score_service = QualityScoreService()


def _build_episode_response(episode: Episode) -> EpisodeQualityMetricsResponse:
	"""Build EpisodeQualityMetricsResponse from an Episode ORM object."""
	raw = episode.generation_progress.get("quality_metrics", {})
	try:
		metrics = QualityMetricsData(**raw)
	except (ValidationError, KeyError, TypeError) as exc:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"Malformed quality_metrics data for episode {episode.id}: {exc}",
		) from exc

	quality_scores = _score_service.calculate_quality_scores(metrics)
	interpretation = _score_service.generate_interpretation(metrics, quality_scores)

	# calculated_at is stored as ISO string; fall back to episode updated_at
	calculated_at_raw = episode.generation_progress.get("calculated_at")
	if calculated_at_raw:
		calculated_at = datetime.fromisoformat(calculated_at_raw)
	else:
		calculated_at = episode.updated_at

	return EpisodeQualityMetricsResponse(
		episode_id=str(episode.id),
		episode_title=episode.episode_metadata.get("title") if episode.episode_metadata else None,
		episode_number=episode.episode_number,
		calculated_at=calculated_at,
		metrics=metrics,
		quality_scores=quality_scores,
		interpretation=interpretation,
	)


def _overall_score(quality_scores: List[QualityScore]) -> float:
	"""Extract overall score from a list of QualityScore objects."""
	for qs in quality_scores:
		if qs.dimension == "overall":
			return qs.score
	return 0.0


@router.get("/episodes/{episode_id}", response_model=EpisodeQualityMetricsResponse)
async def get_episode_quality_metrics(
	episode_id: UUID,
	response: Response,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get quality metrics for a specific episode.

	Retrieves metrics from Episode.generation_progress.quality_metrics.
	Returns 204 No Content if metrics have not yet been calculated.
	Returns 404 if episode not found or belongs to a different tenant.

	Args:
		episode_id: UUID of episode to retrieve metrics for
		response: FastAPI Response object (used to set 204 status)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		EpisodeQualityMetricsResponse with full metrics and interpretation,
		or 204 No Content Response if metrics have not yet been calculated.

	Raises:
		HTTPException: 404 if episode not found or different tenant
		HTTPException: 422 if stored quality_metrics data is malformed
	"""
	result = await db.execute(select(Episode).where(Episode.id == episode_id))
	episode = result.scalar_one_or_none()

	if episode is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

	quality_metrics = (episode.generation_progress or {}).get("quality_metrics")
	if not quality_metrics:
		return Response(status_code=status.HTTP_204_NO_CONTENT)

	return _build_episode_response(episode)


@router.get("/projects/{project_id}", response_model=ProjectQualityMetricsResponse)
async def get_project_quality_metrics(
	project_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get aggregated quality metrics for a project.

	Aggregates metrics from all complete episodes in the project.
	Shows distribution, trends, and best/worst episodes.

	Args:
		project_id: UUID of project
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		ProjectQualityMetricsResponse with aggregated metrics and trends

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	# Verify project exists (RLS enforces tenant isolation)
	project = await db.get(Project, project_id)
	if project is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

	# Fetch all episodes in this project that have quality_metrics
	result = await db.execute(
		select(Episode)
		.where(Episode.project_id == project_id)
		.order_by(Episode.created_at.asc())
	)
	all_episodes = result.scalars().all()

	episodes_with_metrics = [
		ep for ep in all_episodes
		if (ep.generation_progress or {}).get("quality_metrics")
	]

	if not episodes_with_metrics:
		return ProjectQualityMetricsResponse(
			project_id=str(project_id),
			total_episodes_analyzed=0,
			date_range={"earliest": None, "latest": None},
			average_metrics={},
			quality_distribution={"excellent": 0, "good": 0, "fair": 0, "poor": 0},
			quality_scores=[],
			top_episodes=[],
			worst_episodes=[],
			trend={"direction": "stable", "recent_average": 0.0, "previous_average": 0.0, "trend_score": 0.0},
		)

	# Build episode responses for all episodes with metrics
	episode_responses = [_build_episode_response(ep) for ep in episodes_with_metrics]

	# Date range
	calculated_ats = [er.calculated_at for er in episode_responses]
	date_range = {
		"earliest": min(calculated_ats).isoformat(),
		"latest": max(calculated_ats).isoformat(),
	}

	# Average raw metrics
	n = len(episode_responses)
	avg_metrics: Dict[str, Any] = {
		"total_words": round(sum(er.metrics.total_words for er in episode_responses) / n),
		"duration_estimate_minutes": round(
			sum(er.metrics.duration_estimate_minutes for er in episode_responses) / n, 2
		),
		"coherence_score": round(
			sum(er.metrics.coherence_score for er in episode_responses) / n, 4
		),
		"tone": _most_common_tone(episode_responses),
		"speaker_balance_ratio": round(
			sum(er.metrics.speaker_balance_ratio for er in episode_responses) / n, 4
		),
		"is_balanced": sum(1 for er in episode_responses if er.metrics.is_balanced),
		"dialogue_turns": round(sum(er.metrics.dialogue_turns for er in episode_responses) / n),
	}

	# Quality distribution
	distribution: Dict[str, int] = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
	for er in episode_responses:
		overall_qs = next((qs for qs in er.quality_scores if qs.dimension == "overall"), None)
		if overall_qs:
			distribution[overall_qs.rating] = distribution.get(overall_qs.rating, 0) + 1

	# Average quality scores per dimension
	dimensions = ["content_length", "coherence", "balance", "engagement", "overall"]
	avg_quality_scores: List[QualityScore] = []
	for dim in dimensions:
		dim_scores = [
			qs.score
			for er in episode_responses
			for qs in er.quality_scores
			if qs.dimension == dim
		]
		if dim_scores:
			avg_score = sum(dim_scores) / len(dim_scores)
			avg_quality_scores.append(
				QualityScore(dimension=dim, score=round(avg_score, 4), rating=_rating_from_score(avg_score))
			)

	# Top and worst episodes by overall score
	scored_episodes = sorted(
		episode_responses,
		key=lambda er: _overall_score(er.quality_scores),
		reverse=True,
	)

	def _ep_summary(er: EpisodeQualityMetricsResponse) -> Dict[str, Any]:
		overall = _overall_score(er.quality_scores)
		overall_qs = next((qs for qs in er.quality_scores if qs.dimension == "overall"), None)
		return {
			"episode_id": er.episode_id,
			"episode_number": er.episode_number,
			"title": er.episode_title,
			"overall_score": overall,
			"rating": overall_qs.rating if overall_qs else "fair",
		}

	top_episodes = [_ep_summary(er) for er in scored_episodes[:3]]
	# scored_episodes is descending; take last 3 then reverse → worst-first order
	worst_episodes = [_ep_summary(er) for er in reversed(scored_episodes[-3:])]

	# Trend analysis (requires at least 2 episodes)
	trend = _calculate_trend(episode_responses)

	return ProjectQualityMetricsResponse(
		project_id=str(project_id),
		total_episodes_analyzed=n,
		date_range=date_range,
		average_metrics=avg_metrics,
		quality_distribution=distribution,
		quality_scores=avg_quality_scores,
		top_episodes=top_episodes,
		worst_episodes=worst_episodes,
		trend=trend,
	)


@router.get("/projects/{project_id}/episodes", response_model=QualityMetricsListResponse)
async def list_project_episode_metrics(
	project_id: UUID,
	sort_by: Optional[str] = Query(
		"created_at",
		description="Sort field: created_at, overall_score, duration",
	),
	order: str = Query("desc", pattern="^(asc|desc)$"),
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	List quality metrics for all episodes in a project with sorting and pagination.

	Supports sorting by creation date, overall score, or estimated duration.

	Args:
		project_id: UUID of project
		sort_by: Field to sort by (created_at, overall_score, duration)
		order: Sort order (asc/desc)
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of EpisodeQualityMetricsResponse

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	project = await db.get(Project, project_id)
	if project is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

	result = await db.execute(
		select(Episode)
		.where(Episode.project_id == project_id)
		.order_by(Episode.created_at.asc())
	)
	all_episodes = result.scalars().all()

	episodes_with_metrics = [
		ep for ep in all_episodes
		if (ep.generation_progress or {}).get("quality_metrics")
	]

	episode_responses = [_build_episode_response(ep) for ep in episodes_with_metrics]

	# Sort in-memory (metrics are stored in JSONB, not dedicated columns)
	reverse = order == "desc"
	if sort_by == "overall_score":
		episode_responses.sort(key=lambda er: _overall_score(er.quality_scores), reverse=reverse)
	elif sort_by == "duration":
		episode_responses.sort(
			key=lambda er: er.metrics.duration_estimate_minutes, reverse=reverse
		)
	else:
		# Default: sort by calculated_at (proxy for created_at order)
		episode_responses.sort(key=lambda er: er.calculated_at, reverse=reverse)

	total = len(episode_responses)
	total_pages = max(1, (total + page_size - 1) // page_size)
	start = (page - 1) * page_size
	page_items = episode_responses[start : start + page_size]

	return QualityMetricsListResponse(
		episodes=page_items,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages,
	)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _most_common_tone(episode_responses: list) -> str:
	"""Return the most common tone across episode responses."""
	counts: Dict[str, int] = {}
	for er in episode_responses:
		tone = er.metrics.tone
		counts[tone] = counts.get(tone, 0) + 1
	return max(counts, key=lambda k: counts[k]) if counts else "casual"


def _calculate_trend(episode_responses: list) -> Dict[str, Any]:
	"""
	Calculate quality trend from ordered episode responses.

	Splits episodes into two halves (older vs recent) and compares average
	overall scores to determine direction.
	"""
	if len(episode_responses) < 2:
		overall = _overall_score(episode_responses[0].quality_scores) if episode_responses else 0.0
		return {
			"direction": "stable",
			"recent_average": overall,
			"previous_average": overall,
			"trend_score": 0.0,
		}

	mid = len(episode_responses) // 2
	older = episode_responses[:mid]
	recent = episode_responses[mid:]

	prev_avg = sum(_overall_score(er.quality_scores) for er in older) / len(older)
	rec_avg = sum(_overall_score(er.quality_scores) for er in recent) / len(recent)
	trend_score = round(rec_avg - prev_avg, 4)

	if trend_score > 0.02:
		direction = "improving"
	elif trend_score < -0.02:
		direction = "declining"
	else:
		direction = "stable"

	return {
		"direction": direction,
		"recent_average": round(rec_avg, 4),
		"previous_average": round(prev_avg, 4),
		"trend_score": trend_score,
	}
