"""RSSFeed model for podcast RSS feed generation"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class RSSFeed(Base):
    """RSSFeed model for generated RSS feed metadata"""

    __tablename__ = "rss_feeds"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys (one RSS feed per project)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Feed URLs
    s3_key = Column(Text, nullable=True)
    public_url = Column(Text, nullable=True)

    # Validation status (Apple Podcasts, Spotify standards)
    # Structure: {
    #   "last_validated_at": "2025-10-20T00:00:00Z",
    #   "apple_podcasts": {"valid": true, "errors": []},
    #   "spotify": {"valid": true, "errors": []},
    #   "google_podcasts": {"valid": true, "errors": []}
    # }
    validation_status = Column(JSONB, nullable=True, default=dict)

    # Feed metadata
    last_generated = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project")

    def __repr__(self) -> str:
        return f"<RSSFeed(id={self.id}, project_id={self.project_id})>"
