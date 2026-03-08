"""
Audio snippet schemas for request/response validation.

Defines Pydantic models for AudioSnippet CRUD operations with validation
for snippet types, file formats, and audio metadata.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from enum import Enum


class SnippetType(str, Enum):
	"""Valid audio snippet types."""
	intro = "intro"
	outro = "outro"
	midroll = "midroll"
	ad = "ad"
	music = "music"
	other = "other"


class AudioSnippetUpdate(BaseModel):
	"""Schema for updating an existing audio snippet. All fields optional for partial updates."""

	name: Optional[str] = Field(
		None,
		max_length=255,
		description="Snippet name"
	)
	description: Optional[str] = Field(
		None,
		max_length=500,
		description="Optional description"
	)
	snippet_type: Optional[SnippetType] = Field(
		None,
		description="Type of snippet: intro, outro, midroll, ad, music, other"
	)

	@field_validator('name')
	@classmethod
	def validate_name(cls, v: Optional[str]) -> Optional[str]:
		"""Validate name is not empty if provided."""
		if v is not None and not v.strip():
			raise ValueError("name must not be empty")
		return v


class AudioSnippetResponse(BaseModel):
	"""Schema for audio snippet response data."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	project_id: Optional[UUID]
	name: str
	snippet_type: str
	description: Optional[str]
	file_path: str
	s3_key: Optional[str]
	s3_url: Optional[str]
	duration_seconds: Optional[float]
	file_size_bytes: Optional[int]
	file_format: Optional[str]
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class AudioSnippetListResponse(BaseModel):
	"""Schema for paginated audio snippet list response."""

	snippets: list[AudioSnippetResponse]
	total: int = Field(..., description="Total count of snippets")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")


class DownloadUrlResponse(BaseModel):
	"""Schema for presigned download URL response."""

	snippet_id: UUID
	download_url: str = Field(..., description="Presigned S3 URL valid for 1 hour")
	expires_in_seconds: int = Field(default=3600, description="URL expiration time in seconds")
