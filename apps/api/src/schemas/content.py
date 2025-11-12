"""
Pydantic schemas for content source request/response validation.

Provides schemas for creating, updating, and retrieving content sources with
type-specific validation for URL, PDF, and text source types. Each source type
has required fields in source_data that are validated at creation.
"""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from uuid import UUID


# Type alias for supported source types
SourceType = Literal['url', 'pdf', 'text']
ExtractionStatus = Literal['pending', 'extracting', 'complete', 'failed']


class ContentSourceCreate(BaseModel):
    """
    Schema for creating a content source.

    Validates source_data structure based on source_type:
    - url: Requires {"url": str, "title": str}
    - pdf: Requires {"filename": str, "s3_key": str}
    - text: Requires {"content": str}
    """
    episode_id: UUID = Field(..., description="Episode this content source belongs to")
    source_type: SourceType = Field(..., description="Type of content source (url, pdf, text)")
    source_data: Dict[str, Any] = Field(..., description="Source-specific data with required fields")

    @field_validator('source_data')
    @classmethod
    def validate_source_data(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        """
        Validate source_data structure based on source_type.

        Ensures required fields are present and non-empty for each source type.

        Args:
            v: The source_data dictionary
            info: Validation context with other field values

        Returns:
            Validated source_data dictionary

        Raises:
            ValueError: If required fields are missing or empty
        """
        # Get source_type from validation context
        source_type = info.data.get('source_type')

        if source_type == 'url':
            # URL type requires url and title
            if 'url' not in v or not isinstance(v['url'], str) or not v['url'].strip():
                raise ValueError("URL source requires non-empty 'url' field")
            if 'title' not in v or not isinstance(v['title'], str) or not v['title'].strip():
                raise ValueError("URL source requires non-empty 'title' field")

        elif source_type == 'pdf':
            # PDF type requires filename and s3_key
            if 'filename' not in v or not isinstance(v['filename'], str) or not v['filename'].strip():
                raise ValueError("PDF source requires non-empty 'filename' field")
            if 's3_key' not in v or not isinstance(v['s3_key'], str) or not v['s3_key'].strip():
                raise ValueError("PDF source requires non-empty 's3_key' field")

        elif source_type == 'text':
            # Text type requires content
            if 'content' not in v or not isinstance(v['content'], str) or not v['content'].strip():
                raise ValueError("Text source requires non-empty 'content' field")

        return v

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
                "source_type": "pdf",
                "source_data": {
                    "filename": "document.pdf",
                    "s3_key": "uploads/document.pdf"
                }
            },
            {
                "episode_id": "123e4567-e89b-12d3-a456-426614174000",
                "source_type": "text",
                "source_data": {
                    "content": "Raw text content for the podcast"
                }
            }
        ]
    })


class ContentSourceUpdate(BaseModel):
    """
    Schema for updating a content source.

    All fields are optional for partial updates. If source_data is provided,
    it must match the source_type validation rules.
    """
    source_data: Optional[Dict[str, Any]] = Field(None, description="Updated source-specific data")
    extraction_status: Optional[ExtractionStatus] = Field(None, description="Content extraction status")
    extracted_content: Optional[str] = Field(None, description="Extracted text content")
    error_message: Optional[str] = Field(None, description="Error message if extraction failed")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "extraction_status": "complete",
            "extracted_content": "This is the extracted content from the source..."
        }
    })


class ContentSourceResponse(BaseModel):
    """
    Schema for content source response.

    Returns all fields from the ContentSource model including extraction status
    and results as separate fields (not in JSONB).
    """
    id: UUID
    episode_id: UUID
    tenant_id: UUID
    source_type: SourceType
    source_data: Dict[str, Any]
    extraction_status: str
    extracted_content: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContentSourceListResponse(BaseModel):
    """
    Schema for paginated content source list response.

    Includes pagination metadata along with the list of content sources.
    """
    content_sources: list[ContentSourceResponse]
    total: int = Field(..., description="Total number of content sources matching filters")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "content_sources": [],
            "total": 5,
            "page": 1,
            "page_size": 20,
            "total_pages": 1
        }
    })


# Legacy compatibility - keep ExtractionMetadata for backwards compatibility
class ExtractionMetadata(BaseModel):
    """
    Legacy schema for extraction metadata.

    NOTE: This is kept for backwards compatibility but is no longer used
    in the database. The ContentSource model now stores extraction_status,
    extracted_content, and error_message as separate columns.
    """
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
