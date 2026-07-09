"""ContentSource model for episode input sources"""

from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow


class ContentSource(Base):
    """ContentSource model for episode content inputs"""

    __tablename__ = "content_sources"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Source type: 'url', 'pdf', 'youtube', 'text', 'image', 'topic'
    source_type = Column(Text, nullable=False, index=True)

    # Source data - flexible structure based on source_type
    # For URL: {"url": "https://...", "title": "..."}
    # For PDF: {"filename": "doc.pdf", "s3_key": "uploads/...", "mime_type": "application/pdf"}
    # For YouTube: {"url": "https://youtube.com/watch?v=...", "video_id": "..."}
    # For Text: {"content": "raw text content", "title": "..."}
    # For Image: {"filename": "image.jpg", "s3_key": "uploads/...", "mime_type": "image/jpeg"}
    # For Topic: {"topic": "AI in healthcare", "search_results": [...]}
    source_data = Column(JSONB, nullable=False)

    # Extraction status and results (separate columns per migration)
    extraction_status = Column(Text, nullable=False, default='pending', index=True)
    extracted_content = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    episode = relationship("Episode", back_populates="content_sources")

    def __repr__(self) -> str:
        return f"<ContentSource(id={self.id}, type={self.source_type}, status={self.extraction_status})>"
