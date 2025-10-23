"""Project model for podcast organization"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, ForeignKey
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
    title = Column(String(255), nullable=False)
    description = Column(String(2000), nullable=True)

    # Podcast metadata for RSS feed
    # Structure: {
    #   "author": "John Doe",
    #   "category": "Technology",
    #   "language": "en",
    #   "explicit": false,
    #   "image_url": "https://...",
    #   "website_url": "https://...",
    #   "copyright": "© 2024 John Doe"
    # }
    podcast_metadata = Column(JSONB, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="projects")
    episodes = relationship("Episode", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, title={self.title})>"
