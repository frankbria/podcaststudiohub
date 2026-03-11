"""
Episode composition schemas for request/response validation.

Defines Pydantic models for EpisodeComposition operations: creating/updating
timeline layouts, validating compositions, triggering renders, and tracking
render status.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Literal


class TimelineSegment(BaseModel):
	"""Schema for a single segment in the composition timeline."""

	type: Literal["intro", "generated", "outro", "midroll", "ad", "music", "other"] = Field(
		...,
		description="Segment type: 'generated' for main podcast content, others for snippets"
	)
	snippet_id: Optional[UUID] = Field(
		None,
		description="UUID of AudioSnippet to insert (required when type is not 'generated')"
	)
	position_seconds: float = Field(
		0.0,
		ge=0.0,
		description="Position in timeline (seconds) where this segment starts"
	)
	fade_in_ms: int = Field(
		0,
		ge=0,
		le=10000,
		description="Fade-in duration in milliseconds (0-10000)"
	)
	fade_out_ms: int = Field(
		0,
		ge=0,
		le=10000,
		description="Fade-out duration in milliseconds (0-10000)"
	)
	normalize: bool = Field(
		True,
		description="Apply loudness normalization to this segment"
	)
	volume_level: float = Field(
		1.0,
		ge=0.0,
		le=2.0,
		description="Volume multiplier (0.0 to 2.0, 1.0 is original level)"
	)

	@field_validator("snippet_id", mode="before")
	@classmethod
	def validate_snippet_id(cls, v: Optional[UUID], info) -> Optional[UUID]:
		"""snippet_id must be provided for non-generated segments."""
		# Validation of type/snippet_id relationship handled at model level
		return v


class CompositionCreate(BaseModel):
	"""Schema for creating or updating an episode composition layout."""

	timeline: list[TimelineSegment] = Field(
		...,
		min_length=1,
		max_length=50,
		description="Ordered list of timeline segments"
	)
	layout_id: Optional[UUID] = Field(
		None,
		description="Optional episode layout ID to associate with this composition"
	)


class CompositionResponse(BaseModel):
	"""Schema for episode composition response."""

	id: UUID
	episode_id: UUID
	layout_id: Optional[UUID]
	tenant_id: UUID
	timeline: list[dict]
	composition_status: str
	render_status: str
	render_error: Optional[str]
	last_rendered_at: Optional[datetime]
	composed_file_path: Optional[str]
	composed_s3_key: Optional[str]
	composed_s3_url: Optional[str]
	composed_duration_seconds: Optional[float]
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class CompositionValidateResponse(BaseModel):
	"""Schema for composition validation result."""

	valid: bool = Field(..., description="Whether the composition is valid")
	total_duration_seconds: float = Field(
		...,
		description="Estimated total duration of the composition in seconds"
	)
	gaps: list[dict] = Field(
		default_factory=list,
		description="List of silence gaps detected in the timeline"
	)
	warnings: list[str] = Field(
		default_factory=list,
		description="Non-fatal validation warnings"
	)
	errors: list[str] = Field(
		default_factory=list,
		description="Validation errors (present when valid=False)"
	)


class RenderResponse(BaseModel):
	"""Schema for render task trigger response."""

	task_id: str = Field(..., description="Celery task ID for progress tracking")
	status: str = Field(default="queued", description="Initial task status")
	episode_id: UUID
	composition_id: UUID


class RenderStatusResponse(BaseModel):
	"""Schema for render task status response."""

	status: str = Field(..., description="Current render status: queued, processing, complete, failed")
	progress: int = Field(
		0,
		ge=0,
		le=100,
		description="Completion percentage (0-100)"
	)
	eta_seconds: Optional[int] = Field(
		None,
		description="Estimated seconds remaining"
	)
	error: Optional[str] = Field(None, description="Error message if status is 'failed'")
	result: Optional[dict] = Field(None, description="Composition result if status is 'complete'")
