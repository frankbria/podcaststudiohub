"""EpisodeLayout model for composition templates"""

from datetime import datetime
from sqlalchemy import Column, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class EpisodeLayout(Base):
    """EpisodeLayout model for defining snippet positions in episodes"""

    __tablename__ = "episode_layouts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Layout metadata
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    # Layout configuration
    # Structure: {
    #   "segments": [
    #     {
    #       "type": "snippet",
    #       "snippet_id": "uuid",
    #       "position": "pre-roll",
    #       "order": 1
    #     },
    #     {
    #       "type": "main_content",
    #       "position": "auto",
    #       "order": 2
    #     },
    #     {
    #       "type": "snippet",
    #       "snippet_id": "uuid",
    #       "position": "50%",
    #       "order": 3
    #     }
    #   ],
    #   "auto_normalize": true,
    #   "crossfade_duration": 0.5
    # }
    layout_config = Column(JSONB, nullable=False, default=dict)

    # Default flag
    is_default = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    project = relationship("Project")

    def __repr__(self) -> str:
        return f"<EpisodeLayout(id={self.id}, name={self.name})>"
