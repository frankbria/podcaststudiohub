"""Project model for podcast organization"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class Project(Base):
    """Project model for organizing podcast episodes"""

    __tablename__ = "projects"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Basic info
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    # Podcast metadata for RSS feed
    # Structure: {
    #   "show_title": "My Podcast",
    #   "author": "Author Name",
    #   "description": "Podcast description",
    #   "category": "Technology",
    #   "language": "en-US",
    #   "explicit": false,
    #   "copyright": "© 2025 Author",
    #   "artwork_url": "https://s3.../artwork.jpg"
    # }
    podcast_metadata = Column(JSONB, nullable=False, default=dict)

    # Default configurations
    default_tts_config_id = Column(UUID(as_uuid=True), ForeignKey("tts_configurations.id", ondelete="SET NULL"), nullable=True)
    default_template_id = Column(UUID(as_uuid=True), ForeignKey("conversation_templates.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_archived = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="projects")
    episodes = relationship("Episode", back_populates="project", cascade="all, delete-orphan")
    default_tts_config = relationship("TTSConfiguration", foreign_keys=[default_tts_config_id])
    default_template = relationship("ConversationTemplate", foreign_keys=[default_template_id])
    distribution_targets = relationship("DistributionTarget", back_populates="project")
    audio_snippets = relationship("AudioSnippet", back_populates="project")
    episode_layouts = relationship("EpisodeLayout", back_populates="project")
    rss_feed = relationship("RSSFeed", back_populates="project", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name})>"
