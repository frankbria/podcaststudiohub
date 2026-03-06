"""
Quality metrics response schemas for podcast transcript analysis.

Defines Pydantic models for quality metrics retrieval endpoints including
individual episode metrics, project-level aggregations, and paginated lists.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QualityMetricsData(BaseModel):
	"""Raw quality metrics from transcript analysis."""
	total_words: int = Field(..., ge=0, description="Total word count from both speakers")
	duration_estimate_minutes: float = Field(..., ge=0, description="Estimated duration in minutes (150 words/min)")
	coherence_score: float = Field(..., ge=0, le=1, description="Coherence 0.0-1.0 (sentence variation)")
	tone: str = Field(..., description="Detected tone: casual, academic, or humorous")
	speaker_balance_ratio: float = Field(..., ge=0, description="Person1_words / Person2_words ratio")
	is_balanced: bool = Field(..., description="True if balance ratio between 0.3-3.33 (30/70 to 70/30)")
	max_monologue_words: int = Field(..., ge=0, description="Longest segment without speaker turn")
	dialogue_turns: int = Field(..., ge=0, description="Number of Person1 <-> Person2 switches")
	has_good_banter: bool = Field(..., description="True if max_monologue <= 200 AND turns >= 5")


class QualityScore(BaseModel):
	"""Calculated quality score for a specific dimension."""
	dimension: str = Field(..., description="Dimension name: content_length, coherence, balance, engagement, overall")
	score: float = Field(..., ge=0, le=1, description="Score 0.0-1.0")
	rating: str = Field(..., description="poor, fair, good, or excellent")


class Interpretation(BaseModel):
	"""Human-readable interpretation of metrics."""
	overall_rating: str = Field(..., description="Overall quality rating: poor, fair, good, excellent")
	strengths: List[str] = Field(default_factory=list, description="List of quality strengths")
	improvements: List[str] = Field(default_factory=list, description="List of suggested improvements")
	recommendations: Optional[str] = Field(None, description="Specific guidance for improvement")


class EpisodeQualityMetricsResponse(BaseModel):
	"""Quality metrics for a single episode."""
	episode_id: str = Field(..., description="Episode UUID")
	episode_title: Optional[str] = Field(None, description="Episode title from metadata")
	episode_number: Optional[int] = Field(None, description="Episode number if available")
	calculated_at: datetime = Field(..., description="When metrics were calculated")
	metrics: QualityMetricsData
	quality_scores: List[QualityScore] = Field(..., description="Scores for each quality dimension")
	interpretation: Interpretation


class ProjectQualityMetricsResponse(BaseModel):
	"""Aggregated quality metrics for a project."""
	project_id: str = Field(..., description="Project UUID")
	total_episodes_analyzed: int = Field(..., ge=0, description="Number of episodes with metrics")
	date_range: Dict[str, Any] = Field(..., description="Earliest and latest calculated_at timestamps")
	average_metrics: Dict[str, Any] = Field(..., description="Average of all raw metrics across episodes")
	quality_distribution: Dict[str, int] = Field(..., description="Count of episodes per rating tier")
	quality_scores: List[QualityScore] = Field(..., description="Average quality scores across episodes")
	top_episodes: List[Dict[str, Any]] = Field(..., description="Top 3 episodes by overall quality")
	worst_episodes: List[Dict[str, Any]] = Field(..., description="Bottom 3 episodes by overall quality")
	trend: Dict[str, Any] = Field(..., description="Trend analysis: direction, recent/previous averages")


class QualityMetricsListResponse(BaseModel):
	"""Paginated list of episode quality metrics."""
	episodes: List[EpisodeQualityMetricsResponse]
	total: int = Field(..., ge=0, description="Total metrics available")
	page: int = Field(..., ge=1, description="Current page (1-indexed)")
	page_size: int = Field(..., ge=1, le=100, description="Items per page")
	total_pages: int = Field(..., ge=0, description="Total number of pages")
