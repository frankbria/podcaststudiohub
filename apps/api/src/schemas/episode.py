"""
Episode schemas for request/response validation.

Defines Pydantic models for Episode CRUD operations with validation
for episode metadata structure, project relationships, and generation status.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


class EpisodeCreate(BaseModel):
	"""Schema for creating a new episode."""

	project_id: UUID = Field(
		...,
		description="Project this episode belongs to"
	)
	episode_number: Optional[int] = Field(
		None,
		ge=1,
		description="Episode number in sequence (auto-assigned if not provided)"
	)
	episode_metadata: dict = Field(
		...,
		description="JSONB metadata for episode information",
		examples=[{
			"title": "Episode 1: Introduction",
			"description": "Welcome to our first episode",
			"format": "full",
			"explicit": False
		}]
	)

	@field_validator('episode_metadata')
	@classmethod
	def validate_episode_metadata(cls, v: dict) -> dict:
		"""Validate required keys in episode_metadata."""
		required_keys = {'title', 'description'}
		missing_keys = required_keys - set(v.keys())

		if missing_keys:
			raise ValueError(
				f"episode_metadata missing required keys: {', '.join(missing_keys)}"
			)

		# Validate types of required fields
		if not isinstance(v['title'], str) or not v['title'].strip():
			raise ValueError("episode_metadata.title must be a non-empty string")
		if not isinstance(v['description'], str) or not v['description'].strip():
			raise ValueError("episode_metadata.description must be a non-empty string")

		return v


class EpisodeUpdate(BaseModel):
	"""Schema for updating an existing episode. All fields optional for partial updates."""

	episode_number: Optional[int] = Field(
		None,
		ge=1,
		description="Episode number in sequence"
	)
	episode_metadata: Optional[dict] = Field(
		None,
		description="JSONB metadata for episode information"
	)
	generation_status: Optional[str] = Field(
		None,
		description="Generation status (draft, queued, processing, completed, failed)"
	)
	generation_progress: Optional[dict] = Field(
		None,
		description="Generation progress tracking data"
	)
	tts_config_id: Optional[UUID] = Field(
		None,
		description="TTS configuration ID"
	)
	template_id: Optional[UUID] = Field(
		None,
		description="Conversation template ID"
	)
	s3_key: Optional[str] = Field(
		None,
		description="S3 storage key for audio file"
	)
	s3_url: Optional[str] = Field(
		None,
		description="S3 URL for audio file"
	)
	duration_seconds: Optional[float] = Field(
		None,
		description="Audio duration in seconds"
	)
	file_size_bytes: Optional[int] = Field(
		None,
		description="Audio file size in bytes"
	)
	file_path: Optional[str] = Field(
		None,
		description="Local file path"
	)
	transcript_path: Optional[str] = Field(
		None,
		description="Transcript file path"
	)
	task_id: Optional[str] = Field(
		None,
		description="Celery task UUID for tracking background generation job"
	)
	task_started_at: Optional[datetime] = Field(
		None,
		description="When the Celery task was submitted to the broker"
	)
	task_completed_at: Optional[datetime] = Field(
		None,
		description="When the Celery task finished (success or failure)"
	)

	@field_validator('episode_metadata')
	@classmethod
	def validate_episode_metadata(cls, v: Optional[dict]) -> Optional[dict]:
		"""Validate required keys in episode_metadata if provided."""
		if v is None:
			return v

		required_keys = {'title', 'description'}
		missing_keys = required_keys - set(v.keys())

		if missing_keys:
			raise ValueError(
				f"episode_metadata missing required keys: {', '.join(missing_keys)}"
			)

		# Validate types of required fields
		if not isinstance(v['title'], str) or not v['title'].strip():
			raise ValueError("episode_metadata.title must be a non-empty string")
		if not isinstance(v['description'], str) or not v['description'].strip():
			raise ValueError("episode_metadata.description must be a non-empty string")

		return v


class EpisodeResponse(BaseModel):
	"""Schema for episode response data."""

	id: UUID
	project_id: UUID
	user_id: UUID
	tenant_id: UUID
	episode_number: int
	episode_metadata: dict
	generation_status: str
	generation_progress: dict
	file_path: Optional[str]
	s3_key: Optional[str]
	s3_url: Optional[str]
	duration_seconds: Optional[float]
	file_size_bytes: Optional[int]
	transcript_path: Optional[str]
	tts_config_id: Optional[UUID]
	template_id: Optional[UUID]
	# Workflow tracking fields
	platform_ids: Optional[dict] = None
	error_message: Optional[str] = None
	# Celery task tracking fields
	task_id: Optional[str] = None
	task_started_at: Optional[datetime] = None
	task_completed_at: Optional[datetime] = None
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class EpisodeListResponse(BaseModel):
	"""Schema for paginated episode list response."""

	episodes: list[EpisodeResponse]
	total: int = Field(..., description="Total count of episodes")
	page: int = Field(..., description="Current page number")
	page_size: int = Field(..., description="Items per page")
	total_pages: int = Field(..., description="Total number of pages")


class BatchEpisodeCreate(BaseModel):
	"""Schema for batch episode creation request."""

	episodes: list[EpisodeCreate] = Field(
		...,
		min_length=1,
		max_length=50,
		description="List of episodes to create (max 50)"
	)


class BatchEpisodeResult(BaseModel):
	"""Per-episode result in a batch creation response."""

	index: int = Field(..., description="Zero-based index in the request list")
	status: str = Field(..., description="'created' or 'failed'")
	episode: Optional[EpisodeResponse] = Field(None, description="Created episode (if successful)")
	error: Optional[str] = Field(None, description="Error message (if failed)")


class BatchEpisodeResponse(BaseModel):
	"""Schema for batch episode creation response."""

	batch_id: str = Field(..., description="Unique identifier for this batch operation")
	status: str = Field(..., description="'complete' or 'partial'")
	total_episodes: int = Field(..., description="Total episodes in the request")
	created_count: int = Field(..., description="Number of successfully created episodes")
	failed_count: int = Field(..., description="Number of failed episodes")
	results: list[BatchEpisodeResult] = Field(..., description="Per-episode results")
