"""
Analytics schemas for request/response validation.

Defines Pydantic models for analytics event tracking and summary queries.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any, List


VALID_EVENT_TYPES = {"download", "play", "share", "stream"}


class AnalyticsEventCreate(BaseModel):
	"""Schema for tracking an analytics event."""

	event_type: str = Field(
		...,
		description="Type of event: download, play, share, stream"
	)
	episode_id: Optional[UUID] = Field(
		None,
		description="Episode the event is associated with"
	)
	project_id: Optional[UUID] = Field(
		None,
		description="Project the event is associated with"
	)
	metadata: Optional[Dict[str, Any]] = Field(
		None,
		description="Additional event metadata (e.g. duration_listened_seconds, completed)"
	)

	@field_validator('event_type')
	@classmethod
	def validate_event_type(cls, v: str) -> str:
		if v not in VALID_EVENT_TYPES:
			raise ValueError(f"event_type must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}")
		return v


class AnalyticsEventResponse(BaseModel):
	"""Schema for analytics event response."""

	id: UUID
	tenant_id: UUID
	episode_id: Optional[UUID]
	project_id: Optional[UUID]
	event_type: str
	device_type: Optional[str]
	app_name: Optional[str]
	country: Optional[str]
	event_metadata: Optional[Dict[str, Any]]
	created_at: datetime

	model_config = {"from_attributes": True}


class EpisodeAnalyticsSummary(BaseModel):
	"""Aggregated analytics summary for an episode."""

	episode_id: UUID
	period: Dict[str, Optional[str]]
	metrics: Dict[str, int]
	device_breakdown: Dict[str, int]

	model_config = {"from_attributes": True}


class ProjectAnalyticsSummary(BaseModel):
	"""Aggregated analytics summary for a project."""

	project_id: UUID
	period: Dict[str, Any]
	summary: Dict[str, int]
	top_episodes: List[Dict[str, Any]]

	model_config = {"from_attributes": True}
