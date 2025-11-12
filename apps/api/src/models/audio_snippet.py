"""AudioSnippet model for reusable audio files"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, BigInteger, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class AudioSnippet(Base):
    """AudioSnippet model for reusable audio files (intros, outros, ads, music)"""

    __tablename__ = "audio_snippets"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Snippet metadata
    name = Column(Text, nullable=False)
    snippet_type = Column(Text, nullable=False, index=True)  # 'intro', 'outro', 'midroll', 'ad', 'music', 'other'
    description = Column(Text, nullable=True)

    # Audio file information
    file_path = Column(Text, nullable=False)
    s3_key = Column(Text, nullable=True)
    s3_url = Column(Text, nullable=True)

    # Audio properties
    duration_seconds = Column(Numeric(10, 2), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    file_format = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    project = relationship("Project")

    def __repr__(self) -> str:
        return f"<AudioSnippet(id={self.id}, name={self.name}, type={self.snippet_type})>"
