"""ContentSource model for episode input sources"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class ContentSource(Base):
    """ContentSource model for episode content inputs"""

    __tablename__ = "content_sources"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Source type: 'url', 'file', 'youtube', 'text'
    source_type = Column(String(50), nullable=False, index=True)

    # Source data - flexible structure based on source_type
    # For URL: {"url": "https://...", "title": "..."}
    # For File: {"filename": "doc.pdf", "s3_key": "uploads/...", "mime_type": "application/pdf"}
    # For YouTube: {"url": "https://youtube.com/watch?v=...", "video_id": "..."}
    # For Text: {"content": "raw text content", "title": "..."}
    source_data = Column(JSONB, nullable=False)

    # Extracted content metadata
    # Structure: {
    #   "extracted_at": "timestamp",
    #   "word_count": 1500,
    #   "extraction_status": "success" | "failed",
    #   "error_message": "string" (if failed)
    # }
    extraction_metadata = Column(JSONB, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    episode = relationship("Episode", back_populates="content_sources")

    def __repr__(self) -> str:
        return f"<ContentSource(id={self.id}, type={self.source_type})>"
