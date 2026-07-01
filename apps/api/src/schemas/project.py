"""
Project schemas for request/response validation.

Defines Pydantic models for Project CRUD operations with validation
for podcast metadata structure and pagination support.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


class ProjectCreate(BaseModel):
	"""Schema for creating a new project."""

	name: str = Field(
		...,
		min_length=1,
		max_length=255,
		description="Project name"
	)
	description: Optional[str] = Field(
		None,
		description="Project description"
	)
	podcast_metadata: dict = Field(
		...,
		description="JSONB metadata for podcast configuration",
		examples=[{
			"show_title": "My Awesome Podcast",
			"author": "John Doe",
			"description": "A podcast about awesome things",
			"language": "en",
			"explicit": False
		}]
	)

	@field_validator('podcast_metadata')
	@classmethod
	def validate_podcast_metadata(cls, v: dict) -> dict:
		"""Validate podcast_metadata (issue #337).

		Create is lightweight: the UI only collects a title/description at this
		stage, so show_title/author/description are NOT required here. show_title
		is defaulted from the project name in the service layer, and completeness
		(REQUIRED_METADATA_FIELDS) is enforced later at distribution time by
		rss_generation_service. We still reject an empty string for any of these
		keys when it *is* present, to catch obviously-bad input."""
		for key in ('show_title', 'author', 'description'):
			if key in v and (not isinstance(v[key], str) or not v[key].strip()):
				raise ValueError(f"podcast_metadata.{key} must be a non-empty string")

		return v


class ProjectUpdate(BaseModel):
	"""Schema for updating an existing project. All fields optional for partial updates."""

	name: Optional[str] = Field(
		None,
		min_length=1,
		max_length=255,
		description="Project name"
	)
	description: Optional[str] = Field(
		None,
		description="Project description"
	)
	podcast_metadata: Optional[dict] = Field(
		None,
		description="JSONB metadata for podcast configuration"
	)
	default_tts_config_id: Optional[UUID] = Field(
		None,
		description="Default TTS configuration ID"
	)
	default_template_id: Optional[UUID] = Field(
		None,
		description="Default template ID"
	)
	is_archived: Optional[bool] = Field(
		None,
		description="Archive status (soft delete)"
	)

	@field_validator('podcast_metadata')
	@classmethod
	def validate_podcast_metadata(cls, v: Optional[dict]) -> Optional[dict]:
		"""Validate podcast_metadata if provided (issue #337).

		Mirrors ProjectCreate: keys are not required, but an empty string for a
		known field is rejected. Completeness is enforced at distribution time."""
		if v is None:
			return v

		for key in ('show_title', 'author', 'description'):
			if key in v and (not isinstance(v[key], str) or not v[key].strip()):
				raise ValueError(f"podcast_metadata.{key} must be a non-empty string")

		return v


class ProjectResponse(BaseModel):
	"""Schema for project response data."""

	id: UUID
	name: str
	description: Optional[str]
	podcast_metadata: dict
	user_id: UUID
	tenant_id: UUID
	default_tts_config_id: Optional[UUID]
	default_template_id: Optional[UUID]
	is_archived: bool
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
	"""Schema for paginated project list response."""

	projects: list[ProjectResponse]
	total: int = Field(..., description="Total count of projects")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")
