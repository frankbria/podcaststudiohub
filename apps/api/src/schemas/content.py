"""Pydantic schemas for content sources"""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from uuid import UUID


# Type aliases for source types
SourceType = Literal['url', 'file', 'youtube', 'text']


class ContentSourceCreate(BaseModel):
    """Schema for creating a content source"""
    episode_id: UUID = Field(..., description="Parent episode ID")
    source_type: SourceType = Field(..., description="Type of content source")
    source_data: Dict[str, Any] = Field(..., description="Source-specific data")

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "episode_id": "123e4567-e89b-12d3-a456-426614174000",
                "source_type": "url",
                "source_data": {
                    "url": "https://example.com/article",
                    "title": "Tech Article"
                }
            },
            {
                "episode_id": "123e4567-e89b-12d3-a456-426614174000",
                "source_type": "file",
                "source_data": {
                    "filename": "document.pdf",
                    "s3_key": "uploads/document.pdf",
                    "mime_type": "application/pdf"
                }
            },
            {
                "episode_id": "123e4567-e89b-12d3-a456-426614174000",
                "source_type": "youtube",
                "source_data": {
                    "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
                    "video_id": "dQw4w9WgXcQ"
                }
            },
            {
                "episode_id": "123e4567-e89b-12d3-a456-426614174000",
                "source_type": "text",
                "source_data": {
                    "content": "Raw text content for the podcast",
                    "title": "Custom Text Input"
                }
            }
        ]
    })


class ContentSourceResponse(BaseModel):
    """Schema for content source response"""
    id: UUID
    episode_id: UUID
    tenant_id: UUID
    source_type: SourceType
    source_data: Dict[str, Any]
    extraction_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractionMetadata(BaseModel):
    """Schema for content extraction metadata"""
    extracted_at: Optional[datetime] = None
    word_count: Optional[int] = Field(None, ge=0, description="Extracted content word count")
    extraction_status: Literal['pending', 'success', 'failed'] = Field(default='pending')
    error_message: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "extracted_at": "2024-10-20T10:00:00Z",
            "word_count": 1500,
            "extraction_status": "success"
        }
    })
