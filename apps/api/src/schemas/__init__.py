"""Pydantic schemas for request/response validation"""

from .auth import UserCreate, UserLogin, UserResponse, TokenResponse, UserUpdate
from .project import ProjectCreate, ProjectUpdate, ProjectResponse, PodcastMetadata
from .episode import (
    EpisodeCreate,
    EpisodeUpdate,
    EpisodeResponse,
    EpisodeMetadata,
    GenerationProgress,
    GenerationStatus,
)
from .content import ContentSourceCreate, ContentSourceResponse, ExtractionMetadata, SourceType
from .common import PaginationParams, PaginatedResponse, ErrorResponse, SuccessResponse

__all__ = [
    # Auth
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "TokenResponse",
    "UserUpdate",
    # Project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "PodcastMetadata",
    # Episode
    "EpisodeCreate",
    "EpisodeUpdate",
    "EpisodeResponse",
    "EpisodeMetadata",
    "GenerationProgress",
    "GenerationStatus",
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
