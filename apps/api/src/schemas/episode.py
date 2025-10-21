"""Pydantic schemas for episodes"""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


# Type aliases for generation status
GenerationStatus = Literal['draft', 'queued', 'extracting', 'generating', 'synthesizing', 'complete', 'failed']


class EpisodeMetadata(BaseModel):
    """Schema for episode metadata"""
    duration_seconds: Optional[int] = Field(None, ge=0, description="Episode duration in seconds")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="Audio file size in bytes")
    audio_format: str = Field(default="mp3", description="Audio file format")
    sample_rate: int = Field(default=44100, description="Audio sample rate in Hz")
    transcript_url: Optional[str] = Field(None, max_length=1000, description="Transcript file URL")
    pub_date: Optional[datetime] = Field(None, description="Publication date")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "duration_seconds": 300,
            "file_size_bytes": 5242880,
            "audio_format": "mp3",
            "sample_rate": 44100,
            "transcript_url": "https://s3.amazonaws.com/bucket/transcript.txt",
            "pub_date": "2024-10-20T10:00:00Z"
        }
    })


class GenerationProgress(BaseModel):
    """Schema for generation progress tracking"""
    stage: Literal['extracting', 'generating', 'synthesizing', 'complete'] = Field(..., description="Current generation stage")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage (0-100)")
    celery_task_id: Optional[str] = Field(None, description="Celery task ID for tracking")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Generation start time")
    completed_at: Optional[datetime] = Field(None, description="Generation completion time")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stage": "generating",
            "progress": 45,
            "celery_task_id": "abc123-def456-ghi789",
            "started_at": "2024-10-20T10:00:00Z"
        }
    })


class EpisodeCreate(BaseModel):
    """Schema for creating an episode"""
    project_id: UUID = Field(..., description="Parent project ID")
    title: str = Field(..., min_length=1, max_length=255, description="Episode title")
    description: Optional[str] = Field(None, max_length=2000, description="Episode description")
    episode_number: Optional[int] = Field(None, ge=1, description="Episode number in series")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "project_id": "123e4567-e89b-12d3-a456-426614174000",
            "title": "Episode 1: Introduction to AI",
            "description": "An overview of artificial intelligence fundamentals",
            "episode_number": 1
        }
    })


class EpisodeUpdate(BaseModel):
    """Schema for updating an episode"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    episode_number: Optional[int] = Field(None, ge=1)
    metadata: Optional[EpisodeMetadata] = None

    model_config = ConfigDict(from_attributes=True)


class EpisodeResponse(BaseModel):
    """Schema for episode response"""
    id: UUID
    project_id: UUID
    tenant_id: UUID
    title: str
    description: Optional[str] = None
    episode_number: Optional[int] = None
    metadata: Dict[str, Any]
    generation_status: GenerationStatus
    generation_progress: Dict[str, Any]
    audio_s3_key: Optional[str] = None
    audio_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    content_source_count: int = Field(default=0, description="Number of content sources")

    model_config = ConfigDict(from_attributes=True)
