"""Episode model for podcast episodes"""

from datetime import datetime
from sqlalchemy import Column, Text, DateTime, Integer, BigInteger, Numeric, ForeignKey, UniqueConstraint, Index
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

    # Episode number - required, unique per project, auto-assigned if not provided
    episode_number = Column(Integer, nullable=False)

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
    # Values: 'draft', 'queued', 'extracting', 'generating', 'synthesizing',
    #         'uploading', 'composing', 'distributing', 'complete', 'failed',
    #         'distribution_failed'
    # 'distribution_failed' is terminal: the episode generated and uploaded, but
    # one or more platform distributions failed (issue #300).
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

    # Celery task tracking fields
    # task_id: Celery task UUID (e.g. "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
    # Indexed for fast lookups when checking task status or cancelling tasks
    task_id = Column(Text, nullable=True, index=True)

    # When the Celery task began executing
    task_started_at = Column(DateTime(timezone=True), nullable=True)

    # When the Celery task finished (success or failure)
    task_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Platform distribution tracking - maps platform name → platform episode ID
    # Example: {"spotify": "abc123", "apple_podcasts": "xyz789", "webhook": null}
    platform_ids = Column(JSONB, nullable=False, default=dict)

    # Error details when generation_status = 'failed'
    error_message = Column(Text, nullable=True)

    # Configuration overrides
    tts_config_id = Column(UUID(as_uuid=True), ForeignKey("tts_configurations.id", ondelete="SET NULL"), nullable=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("conversation_templates.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    project = relationship("Project", back_populates="episodes")
    content_sources = relationship("ContentSource", back_populates="episode", cascade="all, delete-orphan")
    tts_config = relationship("TTSConfiguration", foreign_keys=[tts_config_id])
    template = relationship("ConversationTemplate", foreign_keys=[template_id])

    __table_args__ = (
        UniqueConstraint('project_id', 'episode_number', name='uq_episodes_project_number'),
        Index('idx_episodes_project_number', 'project_id', 'episode_number'),
    )

    def __repr__(self) -> str:
        title = self.episode_metadata.get('title', 'Untitled') if self.episode_metadata else 'Untitled'
        return f"<Episode(id={self.id}, title={title}, status={self.generation_status})>"
