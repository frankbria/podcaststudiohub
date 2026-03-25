"""Pydantic schemas for analytics endpoints"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from ..models.analytics_event import VALID_EVENT_TYPES


class TrackEventRequest(BaseModel):
	"""Request body for POST /analytics/events"""

	event_type: str
	episode_id: Optional[UUID] = None
	project_id: Optional[UUID] = None
	metadata: Optional[Dict[str, Any]] = None

	@field_validator("event_type")
	@classmethod
	def validate_event_type(cls, v: str) -> str:
		if v not in VALID_EVENT_TYPES:
			raise ValueError(f"event_type must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}")
		return v


class AnalyticsEventResponse(BaseModel):
	"""Response schema for a tracked event"""

	id: UUID
	event_type: str
	episode_id: Optional[UUID]
	project_id: Optional[UUID]
	event_metadata: Optional[Dict[str, Any]]
	created_at: datetime

	model_config = {"from_attributes": True}


class EpisodeAnalyticsResponse(BaseModel):
	"""Aggregated analytics for a single episode"""

	episode_id: UUID
	period: Dict[str, Optional[datetime]]
	metrics: Dict[str, Any]
	device_breakdown: Dict[str, int]
	app_breakdown: Dict[str, int]
	top_countries: List[Dict[str, Any]]


class ProjectAnalyticsResponse(BaseModel):
	"""Aggregated analytics for a project (30-day summary)"""

	project_id: UUID
	period: Dict[str, Any]
	summary: Dict[str, Any]
	trends: Dict[str, Any]
	top_episodes: List[Dict[str, Any]]
