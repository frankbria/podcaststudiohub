"""
Episode composition schemas for request/response validation.

Defines Pydantic models for EpisodeComposition CRUD operations including
timeline segment definitions, layout validation results, and render status.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from enum import Enum


class CompositionStatus(str, Enum):
	"""Valid composition status values."""
	draft = "draft"
	preview = "preview"
	final = "final"


class RenderStatus(str, Enum):
	"""Valid render status values."""
	pending = "pending"
	composing = "composing"
	complete = "complete"
	failed = "failed"


class TimelineSegment(BaseModel):
	"""A single segment in the episode composition timeline."""

	type: Literal["intro", "generated", "outro", "midroll", "ad"] = Field(
		..., description="Type of audio segment"
	)
	snippet_id: Optional[UUID] = Field(
		None,
		description="UUID of AudioSnippet (required for non-generated segments)"
	)
	position_seconds: float = Field(
		...,
		ge=0,
		description="Position in timeline in seconds"
	)
	fade_in_ms: int = Field(
		default=0,
		ge=0,
		le=10000,
		description="Fade-in duration in milliseconds"
	)
	fade_out_ms: int = Field(
		default=0,
		ge=0,
		le=10000,
		description="Fade-out duration in milliseconds"
	)
	normalize: bool = Field(
		default=True,
		description="Whether to normalize audio loudness"
	)
	volume_level: float = Field(
		default=1.0,
		ge=0.0,
		le=2.0,
		description="Volume multiplier (0.0 to 2.0)"
	)

	@model_validator(mode="after")
	def validate_snippet_id_required(self) -> "TimelineSegment":
		"""Ensure snippet_id is provided for non-generated segments."""
		if self.type != "generated" and self.snippet_id is None:
			raise ValueError(
				f"snippet_id is required for segment type '{self.type}'"
			)
		return self


class CompositionLayoutCreate(BaseModel):
	"""Schema for creating or updating an episode composition layout."""

	timeline: List[TimelineSegment] = Field(
		...,
		min_length=1,
		description="Ordered list of timeline segments"
	)

	@field_validator("timeline")
	@classmethod
	def validate_timeline_not_empty(
		cls, v: List[TimelineSegment]
	) -> List[TimelineSegment]:
		"""Validate timeline has at least one segment."""
		if not v:
			raise ValueError("Timeline must contain at least one segment")
		return v


class GapInfo(BaseModel):
	"""Information about a silence gap in the composition."""

	start_seconds: float
	end_seconds: float
	duration_seconds: float


class ValidationResult(BaseModel):
	"""Result of composition layout validation."""

	valid: bool
	total_duration: float = Field(description="Total estimated duration in seconds")
	gaps: List[GapInfo] = Field(default_factory=list, description="Silence gaps detected")
	warnings: List[str] = Field(default_factory=list, description="Validation warnings")


class CompositionResponse(BaseModel):
	"""Schema for episode composition response data."""

	id: UUID
	episode_id: UUID
	layout_id: Optional[UUID]
	tenant_id: UUID
	timeline: List[Dict[str, Any]]
	composition_status: str
	composed_file_path: Optional[str]
	composed_s3_key: Optional[str]
	composed_s3_url: Optional[str]
	composed_duration_seconds: Optional[float]
	render_status: Optional[str]
	render_error: Optional[str]
	last_rendered_at: Optional[datetime]
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class RenderResponse(BaseModel):
	"""Schema for composition render trigger response."""

	task_id: str
	status: str = "queued"
	episode_id: str
	composition_id: str


class CompositionStatusResponse(BaseModel):
	"""Schema for composition task status response."""

	task_id: str
	status: str = Field(description="Task status: pending, composing, complete, failed")
	progress: int = Field(default=0, ge=0, le=100, description="Completion percentage")
	eta_seconds: Optional[int] = Field(None, description="Estimated time to completion")
	error: Optional[str] = Field(None, description="Error message if failed")
	result: Optional[Dict[str, Any]] = Field(None, description="Task result if complete")
