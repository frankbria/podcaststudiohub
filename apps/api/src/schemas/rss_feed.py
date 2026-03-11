"""
RSS Feed schemas for request/response validation.

Defines Pydantic models for RSS Feed management endpoints.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import List, Optional


class RSSFeedResponse(BaseModel):
	"""Schema for RSS feed response data."""

	id: UUID
	project_id: UUID
	tenant_id: UUID
	s3_key: Optional[str] = None
	public_url: Optional[str] = None
	validation_status: Optional[dict] = None
	last_generated: Optional[datetime] = None
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class PodcastMetadataUpdate(BaseModel):
	"""Schema for updating podcast metadata fields that affect RSS output."""

	show_title: Optional[str] = Field(None, description="Podcast show title")
	author: Optional[str] = Field(None, description="Podcast author name")
	description: Optional[str] = Field(None, description="Podcast description")
	category: Optional[str] = Field(None, description="Podcast category (e.g. Technology)")
	language: Optional[str] = Field(None, description="BCP 47 language code (e.g. en-US)")
	explicit: Optional[bool] = Field(None, description="Whether podcast contains explicit content")
	copyright: Optional[str] = Field(None, description="Copyright statement")
	artwork_url: Optional[str] = Field(None, description="URL of podcast artwork image")
	website_url: Optional[str] = Field(None, description="Podcast website URL")


class RSSFeedUpdate(BaseModel):
	"""Schema for updating RSS feed metadata."""

	podcast_metadata: PodcastMetadataUpdate = Field(
		...,
		description="Podcast metadata fields to update (triggers feed regeneration)"
	)


class PlatformValidationResult(BaseModel):
	"""Validation result for a single podcast platform."""

	valid: bool = Field(..., description="Whether the feed is valid for this platform")
	errors: List[str] = Field(default_factory=list, description="List of validation errors")


class RSSValidationStatusResponse(BaseModel):
	"""Validation status for all podcast platforms."""

	last_validated_at: Optional[str] = Field(None, description="ISO timestamp of last validation")
	apple_podcasts: Optional[PlatformValidationResult] = Field(None, description="Apple Podcasts validation")
	spotify: Optional[PlatformValidationResult] = Field(None, description="Spotify validation")
	google_podcasts: Optional[PlatformValidationResult] = Field(None, description="Google Podcasts validation")

	model_config = {"from_attributes": True}


class RSSValidationTriggerResponse(BaseModel):
	"""Response when validation/generation is triggered as a background task."""

	task_id: str = Field(..., description="Celery task ID")
	status: str = Field(..., description="Task dispatch status")
	message: str = Field(..., description="Human-readable status message")
