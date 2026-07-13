"""
RSS Feed schemas for request/response validation.

Defines Pydantic models for RSS Feed management endpoints.
"""

from pydantic import BaseModel, Field, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


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

	@model_validator(mode="after")
	def reject_clearing_required_fields(self):
		"""Explicitly-sent null/blank values delete keys on merge (#381), but the
		fields required for feed generation must never be cleared. Rejecting here
		keeps the 422 ahead of the DB write in the update route."""
		for key in ("show_title", "author", "description"):
			if key in self.model_fields_set:
				value = getattr(self, key)
				if value is None or not value.strip():
					raise ValueError(f"podcast_metadata.{key} cannot be cleared")
		return self


class RSSFeedUpdate(BaseModel):
	"""Schema for updating RSS feed metadata."""

	podcast_metadata: PodcastMetadataUpdate = Field(
		...,
		description="Podcast metadata fields to update (triggers feed regeneration)"
	)
