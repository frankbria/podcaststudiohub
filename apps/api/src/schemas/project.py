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
		"""Validate required keys in podcast_metadata."""
		required_keys = {'show_title', 'author', 'description'}
		missing_keys = required_keys - set(v.keys())

		if missing_keys:
			raise ValueError(
				f"podcast_metadata missing required keys: {', '.join(missing_keys)}"
			)

		# Validate types of required fields
		if not isinstance(v['show_title'], str) or not v['show_title'].strip():
			raise ValueError("podcast_metadata.show_title must be a non-empty string")
		if not isinstance(v['author'], str) or not v['author'].strip():
			raise ValueError("podcast_metadata.author must be a non-empty string")
		if not isinstance(v['description'], str) or not v['description'].strip():
			raise ValueError("podcast_metadata.description must be a non-empty string")

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
		"""Validate required keys in podcast_metadata if provided."""
		if v is None:
			return v

		required_keys = {'show_title', 'author', 'description'}
		missing_keys = required_keys - set(v.keys())

		if missing_keys:
			raise ValueError(
				f"podcast_metadata missing required keys: {', '.join(missing_keys)}"
			)

		# Validate types of required fields
		if not isinstance(v['show_title'], str) or not v['show_title'].strip():
			raise ValueError("podcast_metadata.show_title must be a non-empty string")
		if not isinstance(v['author'], str) or not v['author'].strip():
			raise ValueError("podcast_metadata.author must be a non-empty string")
		if not isinstance(v['description'], str) or not v['description'].strip():
			raise ValueError("podcast_metadata.description must be a non-empty string")

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
