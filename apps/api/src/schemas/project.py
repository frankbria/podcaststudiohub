"""Pydantic schemas for projects"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


class PodcastMetadata(BaseModel):
    """Schema for podcast RSS metadata"""
    author: Optional[str] = Field(None, max_length=255, description="Podcast author name")
    category: Optional[str] = Field(None, max_length=100, description="Podcast category")
    language: str = Field(default="en", max_length=10, description="Podcast language code")
    explicit: bool = Field(default=False, description="Contains explicit content")
    image_url: Optional[str] = Field(None, max_length=1000, description="Podcast cover image URL")
    website_url: Optional[str] = Field(None, max_length=1000, description="Podcast website URL")
    copyright: Optional[str] = Field(None, max_length=255, description="Copyright notice")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "author": "John Doe",
            "category": "Technology",
            "language": "en",
            "explicit": False,
            "image_url": "https://example.com/cover.jpg",
            "website_url": "https://example.com",
            "copyright": "© 2024 John Doe"
        }
    })


class ProjectCreate(BaseModel):
    """Schema for creating a project"""
    title: str = Field(..., min_length=1, max_length=255, description="Project title")
    description: Optional[str] = Field(None, max_length=2000, description="Project description")
    podcast_metadata: PodcastMetadata = Field(default_factory=PodcastMetadata, description="Podcast RSS metadata")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "title": "Tech Insights Podcast",
            "description": "Weekly deep dives into emerging technologies",
            "podcast_metadata": {
                "author": "John Doe",
                "category": "Technology",
                "language": "en"
            }
        }
    })


class ProjectUpdate(BaseModel):
    """Schema for updating a project"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    podcast_metadata: Optional[PodcastMetadata] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    """Schema for project response"""
    id: UUID
    user_id: UUID
    tenant_id: UUID
    title: str
    description: Optional[str] = None
    podcast_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    episode_count: int = Field(default=0, description="Number of episodes in this project")

    model_config = ConfigDict(from_attributes=True)
