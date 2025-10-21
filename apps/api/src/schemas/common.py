"""Common Pydantic schemas used across the API"""

from typing import Optional, Any, List, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict


class PaginationParams(BaseModel):
    """Schema for pagination query parameters"""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Number of items per page (max 100)")

    @property
    def offset(self) -> int:
        """Calculate offset from page and page_size"""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for page_size"""
        return self.page_size

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "page": 1,
            "page_size": 20
        }
    })


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response schema"""
    items: List[T] = Field(..., description="List of items for current page")
    total: int = Field(..., ge=0, description="Total number of items")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Schema for error responses"""
    error: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Any] = Field(None, description="Additional error details")

    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "error": "ValidationError",
                "message": "Invalid email format",
                "details": {"field": "email", "value": "invalid-email"}
            },
            {
                "error": "NotFound",
                "message": "Episode not found",
                "details": {"episode_id": "123e4567-e89b-12d3-a456-426614174000"}
            },
            {
                "error": "Unauthorized",
                "message": "Invalid or expired token"
            }
        ]
    })


class SuccessResponse(BaseModel):
    """Schema for generic success responses"""
    success: bool = Field(default=True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: Optional[Any] = Field(None, description="Optional response data")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Episode deleted successfully",
            "data": {"id": "123e4567-e89b-12d3-a456-426614174000"}
        }
    })
