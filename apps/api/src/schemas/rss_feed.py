"""
RSS Feed schemas for request/response validation.

Defines Pydantic models for RSS Feed management endpoints and
RSS feed validation against podcast directories.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Literal, Optional, List


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


# --- RSS Feed Validation Schemas ---


class ValidationError(BaseModel):
	"""Single validation error or warning."""

	field: str = Field(..., description="XML field path, e.g. 'itunes:image', 'enclosure/@type'")
	level: Literal['error', 'warning'] = Field(
		...,
		description="'error' blocks submission, 'warning' is advisory"
	)
	message: str = Field(..., description="User-friendly error message")
	details: Optional[str] = Field(None, description="Technical details for troubleshooting")
	examples: Optional[List[str]] = Field(None, description="Examples of correct format")


class DirectoryValidationResult(BaseModel):
	"""Validation results for one podcast directory."""

	directory: Literal['apple_podcasts', 'spotify', 'google_podcasts']
	valid: bool = Field(..., description="True if no errors (warnings allowed)")
	errors: List[ValidationError] = Field(default_factory=list)
	warnings: List[ValidationError] = Field(default_factory=list)
	checked_at: datetime


class ValidationStatusUpdate(BaseModel):
	"""Complete validation results for all directories.

	This structure is stored in RSSFeed.validation_status JSONB field
	and returned from the validation endpoints.
	"""

	last_validated_at: datetime
	apple_podcasts: DirectoryValidationResult
	spotify: DirectoryValidationResult
	google_podcasts: DirectoryValidationResult
	is_valid_for_all: bool = Field(
		...,
		description="True if all three directories have valid=True"
	)
