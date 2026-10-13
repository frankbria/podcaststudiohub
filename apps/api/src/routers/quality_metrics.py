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

	Aggregates metrics from every episode in the project that has them, oldest
	first: distribution, averages, trend, and best/worst episodes.

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	episode_responses = await _project_episode_responses(db, project_id)
	if not episode_responses:
		return _empty_project_response(project_id)

	calculated_ats = [er.calculated_at for er in episode_responses]
	ranked = sorted(episode_responses, key=lambda er: _overall_score(er.quality_scores), reverse=True)
	return ProjectQualityMetricsResponse(
		project_id=str(project_id),
		total_episodes_analyzed=len(episode_responses),
		date_range={"earliest": min(calculated_ats).isoformat(), "latest": max(calculated_ats).isoformat()},
		average_metrics=_average_metrics(episode_responses),
		quality_distribution=_quality_distribution(episode_responses),
		quality_scores=_average_quality_scores(episode_responses),
		top_episodes=[_episode_summary(er) for er in ranked[:3]],
		# ranked is best-first; the last three, reversed, are worst-first
		worst_episodes=[_episode_summary(er) for er in reversed(ranked[-3:])],
		trend=_calculate_trend(episode_responses),
	)


# Sort keys for the episode list; anything else sorts by calculated_at.
_LIST_SORT_KEYS = {
	"overall_score": lambda er: _overall_score(er.quality_scores),
	"duration": lambda er: er.metrics.duration_estimate_minutes,
}


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

	Sorts in memory (metrics live in JSONB, not columns) by creation date,
	overall score, or estimated duration.

	Raises:
		HTTPException: 404 if project not found or different tenant
	"""
	episode_responses = await _project_episode_responses(db, project_id)
	sort_key = _LIST_SORT_KEYS.get(sort_by, lambda er: er.calculated_at)
	episode_responses.sort(key=sort_key, reverse=order == "desc")

	total = len(episode_responses)
	start = (page - 1) * page_size
	return QualityMetricsListResponse(
		episodes=episode_responses[start : start + page_size],
		total=total,
		page=page,
		page_size=page_size,
		total_pages=max(1, (total + page_size - 1) // page_size),
	)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _project_episode_responses(
	db: AsyncSession, project_id: UUID
) -> List[EpisodeQualityMetricsResponse]:
	"""Scored responses for the project's episodes that have metrics, oldest
	first. 404 when the project is missing or another tenant's (RLS)."""
	if await db.get(Project, project_id) is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
	result = await db.execute(
		select(Episode)
		.where(Episode.project_id == project_id)
		.order_by(Episode.created_at.asc())
	)
	return [
		_build_episode_response(ep)
		for ep in result.scalars().all()
		if (ep.generation_progress or {}).get("quality_metrics")
	]


def _empty_project_response(project_id: UUID) -> ProjectQualityMetricsResponse:
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


def _mean(values: list) -> float:
	return sum(values) / len(values)


def _average_metrics(episode_responses: list) -> Dict[str, Any]:
	"""Average raw metrics. The balance ratio averages only the episodes that
	have one: a script whose guest never speaks stores null (#570)."""
	metrics = [er.metrics for er in episode_responses]
	return {
		"total_words": round(_field_mean(metrics, "total_words")),
		"duration_estimate_minutes": round(_field_mean(metrics, "duration_estimate_minutes"), 2),
		"coherence_score": round(_field_mean(metrics, "coherence_score"), 4),
		"tone": _most_common_tone(episode_responses),
		"speaker_balance_ratio": _mean_ratio(metrics),
		"is_balanced": sum(m.is_balanced for m in metrics),
		"dialogue_turns": round(_field_mean(metrics, "dialogue_turns")),
	}


def _field_mean(metrics: list, field: str) -> float:
	return _mean([getattr(m, field) for m in metrics])


def _mean_ratio(metrics: list) -> Optional[float]:
	ratios = [m.speaker_balance_ratio for m in metrics if m.speaker_balance_ratio is not None]
	return round(_mean(ratios), 4) if ratios else None


def _overall(quality_scores: List[QualityScore]) -> Optional[QualityScore]:
	return next((qs for qs in quality_scores if qs.dimension == "overall"), None)


def _quality_distribution(episode_responses: list) -> Dict[str, int]:
	"""Episodes per overall rating tier."""
	distribution: Dict[str, int] = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
	ratings = [_overall(er.quality_scores) for er in episode_responses]
	for overall in filter(None, ratings):
		distribution[overall.rating] = distribution.get(overall.rating, 0) + 1
	return distribution


def _average_quality_scores(episode_responses: list) -> List[QualityScore]:
	"""Each dimension's mean score across episodes, in the scorer's order."""
	by_dimension: Dict[str, List[float]] = {}
	for er in episode_responses:
		for qs in er.quality_scores:
			by_dimension.setdefault(qs.dimension, []).append(qs.score)
	return [_averaged(dim, scores) for dim, scores in by_dimension.items()]


def _averaged(dimension: str, scores: List[float]) -> QualityScore:
	avg = _mean(scores)
	return QualityScore(dimension=dimension, score=round(avg, 4), rating=_rating_from_score(avg))


def _episode_summary(er: EpisodeQualityMetricsResponse) -> Dict[str, Any]:
	overall = _overall(er.quality_scores)
	return {
		"episode_id": er.episode_id,
		"episode_number": er.episode_number,
		"title": er.episode_title,
		"overall_score": _overall_score(er.quality_scores),
		"rating": overall.rating if overall else "fair",
	}


def _most_common_tone(episode_responses: list) -> str:
	"""Return the most common tone across episode responses."""
	counts: Dict[str, int] = {}
	for er in episode_responses:
		tone = er.metrics.tone
		counts[tone] = counts.get(tone, 0) + 1
	return max(counts, key=lambda k: counts[k]) if counts else "casual"


def _trend_direction(trend_score: float) -> str:
	if trend_score > 0.02:
		return "improving"
	if trend_score < -0.02:
		return "declining"
	return "stable"


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
	prev_avg = _mean([_overall_score(er.quality_scores) for er in episode_responses[:mid]])
	rec_avg = _mean([_overall_score(er.quality_scores) for er in episode_responses[mid:]])
	trend_score = round(rec_avg - prev_avg, 4)
	return {
		"direction": _trend_direction(trend_score),
		"recent_average": round(rec_avg, 4),
		"previous_average": round(prev_avg, 4),
		"trend_score": trend_score,
	}
