"""Episode model for podcast episodes"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class Episode(Base):
    """Episode model for individual podcast episodes"""

    __tablename__ = "episodes"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Basic info
    title = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)
    episode_number = Column(Integer, nullable=True)

    # Episode metadata
    # Structure: {
    #   "duration_seconds": 300,
    #   "file_size_bytes": 5242880,
    #   "audio_format": "mp3",
    #   "sample_rate": 44100,
    #   "transcript_url": "https://...",
    #   "pub_date": "2024-10-20T10:00:00Z"
    # }
    metadata = Column(JSONB, nullable=False, default=dict)

    # Generation status tracking
    # Values: 'draft', 'queued', 'extracting', 'generating', 'synthesizing', 'complete', 'failed'
    generation_status = Column(String(50), nullable=False, default='draft', index=True)

    # Generation progress tracking
    # Structure: {
    #   "stage": "extracting" | "generating" | "synthesizing" | "complete",
    #   "progress": 0-100,
    #   "celery_task_id": "uuid",
    #   "error_message": "string" (if failed),
    #   "started_at": "timestamp",
    #   "completed_at": "timestamp"
    # }
    generation_progress = Column(JSONB, nullable=False, default=dict)

    # Audio storage
    audio_s3_key = Column(String(500), nullable=True)  # S3 object key
    audio_url = Column(String(1000), nullable=True)    # Public URL for playback

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="episodes")
    content_sources = relationship("ContentSource", back_populates="episode", cascade="all, delete-orphan")
    audio_snippets = relationship("AudioSnippet", back_populates="episode", cascade="all, delete-orphan")
    episode_layouts = relationship("EpisodeLayout", back_populates="episode", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, title={self.title}, status={self.generation_status})>"
