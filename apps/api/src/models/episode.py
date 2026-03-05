"""Episode model for podcast episodes"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Integer, BigInteger, Numeric, ForeignKey
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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Episode number (can be null for unnumbered episodes)
    episode_number = Column(Integer, nullable=True)

    # Episode metadata (title, description, episode_number stored here per migration 002)
    # Structure: {
    #   "title": "Episode Title",
    #   "description": "Episode description",
    #   "episode_number": 1,
    #   "season_number": 1,
    #   "publication_date": "2025-10-20T00:00:00Z",
    #   "tags": ["tech", "ai", "podcast"],
    #   "duration_seconds": 300,
    #   "file_size_bytes": 5242880,
    #   "format": "conversation"
    # }
    episode_metadata = Column(JSONB, nullable=False, default=dict)

    # File paths and storage
    file_path = Column(Text, nullable=True)
    s3_key = Column(Text, nullable=True)
    s3_url = Column(Text, nullable=True)
    duration_seconds = Column(Numeric(10, 2), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    transcript_path = Column(Text, nullable=True)

    # Generation status tracking
    # Values: 'draft', 'queued', 'extracting', 'generating', 'synthesizing', 'complete', 'failed'
    generation_status = Column(Text, nullable=False, default='draft', index=True)

    # Generation progress tracking
    # Structure: {
    #   "stage": "extracting" | "generating" | "synthesizing" | "complete",
    #   "progress": 0-100,
    #   "error_message": "string" (if failed),
    #   "started_at": "timestamp",
    #   "completed_at": "timestamp"
    # }
    generation_progress = Column(JSONB, nullable=False, default=dict)

    # Configuration overrides
    tts_config_id = Column(UUID(as_uuid=True), ForeignKey("tts_configurations.id", ondelete="SET NULL"), nullable=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("conversation_templates.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="episodes")
    project = relationship("Project", back_populates="episodes")
    content_sources = relationship("ContentSource", back_populates="episode", cascade="all, delete-orphan")
    tts_config = relationship("TTSConfiguration", back_populates="episodes", foreign_keys=[tts_config_id])
    template = relationship("ConversationTemplate", back_populates="episodes", foreign_keys=[template_id])
    composition = relationship("EpisodeComposition", back_populates="episode", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        title = self.episode_metadata.get('title', 'Untitled') if self.episode_metadata else 'Untitled'
        return f"<Episode(id={self.id}, title={title}, status={self.generation_status})>"
