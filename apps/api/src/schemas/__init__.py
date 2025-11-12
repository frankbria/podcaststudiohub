"""Pydantic schemas for request/response validation"""

from .auth import UserRegister, UserLogin, UserResponse, TokenResponse, UserUpdate
from .project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse
from .episode import (
    EpisodeCreate,
    EpisodeUpdate,
    EpisodeResponse,
    EpisodeListResponse,
)
from .content import ContentSourceCreate, ContentSourceResponse, ExtractionMetadata, SourceType
from .common import PaginationParams, PaginatedResponse, ErrorResponse, SuccessResponse

__all__ = [
    # Auth
    "UserRegister",
    "UserLogin",
    "UserResponse",
    "TokenResponse",
    "UserUpdate",
    # Project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "ProjectListResponse",
    # Episode
    "EpisodeCreate",
    "EpisodeUpdate",
    "EpisodeResponse",
    "EpisodeListResponse",
    # Content
    "ContentSourceCreate",
    "ContentSourceResponse",
    "ExtractionMetadata",
    "SourceType",
    # Common
    "PaginationParams",
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
]
