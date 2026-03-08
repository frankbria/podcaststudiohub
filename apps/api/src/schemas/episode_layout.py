"""
Episode layout schemas for request/response validation.

Defines Pydantic models for EpisodeLayout CRUD operations with validation
for layout configuration structure, segment types, positions, and main_content
requirement.
"""

import re
from pydantic import BaseModel, Field, field_validator, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, Literal


class LayoutSegment(BaseModel):
	"""Schema for an individual segment in layout_config."""

	type: Literal["snippet", "main_content"] = Field(
		...,
		description="Segment type: 'snippet' for audio snippet, 'main_content' for main podcast content"
	)
	snippet_id: Optional[UUID] = Field(
		None,
		description="UUID of AudioSnippet to insert (required when type='snippet')"
	)
	position: str = Field(
		...,
		description="Segment position: 'pre-roll', 'post-roll', 'auto', or timestamp 'MM:SS' / 'MM:SS.mmm'"
	)
	order: int = Field(
		...,
		ge=1,
		description="1-based segment order"
	)

	@model_validator(mode="after")
	def validate_snippet_requirement(self) -> "LayoutSegment":
		"""Ensure snippet_id is provided when type is 'snippet'."""
		if self.type == "snippet" and self.snippet_id is None:
			raise ValueError("snippet_id is required when segment type is 'snippet'")
		if self.type == "main_content" and self.snippet_id is not None:
			raise ValueError("snippet_id must not be provided for main_content segments")
		return self

	@field_validator("position")
	@classmethod
	def validate_position(cls, v: str) -> str:
		"""Validate position value is a recognized keyword or valid timestamp."""
		valid_keywords = {"pre-roll", "post-roll", "auto"}
		if v in valid_keywords:
			return v
		# Validate timestamp format: MM:SS or MM:SS.mmm
		timestamp_pattern = r"^\d+:[0-5]\d(\.\d{1,3})?$"
		if re.match(timestamp_pattern, v):
			return v
		raise ValueError(
			f"Invalid position '{v}'. Must be 'pre-roll', 'post-roll', 'auto', or a timestamp like '1:30' or '1:30.500'"
		)


class LayoutConfig(BaseModel):
	"""Schema for the layout_config JSONB structure."""

	segments: list[LayoutSegment] = Field(
		...,
		min_length=1,
		max_length=20,
		description="List of segments in the layout"
	)
	auto_normalize: bool = Field(
		True,
		description="Automatically normalize audio volumes between segments"
	)
	crossfade_duration: float = Field(
		0.5,
		ge=0.0,
		le=5.0,
		description="Crossfade duration in seconds between segments (0.0-5.0)"
	)

	@model_validator(mode="after")
	def validate_segments(self) -> "LayoutConfig":
		"""Validate segment rules: exactly one main_content, unique orders."""
		main_content_segments = [s for s in self.segments if s.type == "main_content"]

		if len(main_content_segments) == 0:
			raise ValueError(
				"Layout must contain exactly one main_content segment, found: 0"
			)
		if len(main_content_segments) > 1:
			raise ValueError(
				f"Layout must contain exactly one main_content segment, found: {len(main_content_segments)}"
			)

		# Validate order values are unique and consecutive starting from 1
		orders = sorted([s.order for s in self.segments])
		expected = list(range(1, len(self.segments) + 1))
		if orders != expected:
			raise ValueError(
				f"Segment ordering must be consecutive 1-{len(self.segments)}, got: {orders}"
			)

		return self


class EpisodeLayoutCreate(BaseModel):
	"""Schema for creating a new episode layout."""

	name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Layout name"
	)
	description: Optional[str] = Field(
		None,
		description="Optional description of the layout"
	)
	project_id: Optional[UUID] = Field(
		None,
		description="Optional project ID for project-scoped layouts"
	)
	layout_config: LayoutConfig = Field(
		...,
		description="Layout configuration with segments and audio settings"
	)
	is_default: bool = Field(
		False,
		description="Set as default layout for the tenant"
	)


class EpisodeLayoutUpdate(BaseModel):
	"""Schema for updating an existing episode layout. All fields optional for partial updates."""

	name: Optional[str] = Field(
		None,
		min_length=1,
		max_length=255,
		description="Layout name"
	)
	description: Optional[str] = Field(
		None,
		description="Optional description of the layout"
	)
	layout_config: Optional[LayoutConfig] = Field(
		None,
		description="Layout configuration with segments and audio settings"
	)
	is_default: Optional[bool] = Field(
		None,
		description="Set as default layout for the tenant"
	)


class EpisodeLayoutResponse(BaseModel):
	"""Schema for episode layout response data."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	project_id: Optional[UUID]
	name: str
	description: Optional[str]
	layout_config: dict
	is_default: bool
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class EpisodeLayoutListResponse(BaseModel):
	"""Schema for paginated episode layout list response."""

	layouts: list[EpisodeLayoutResponse]
	total: int = Field(..., description="Total count of layouts")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")
