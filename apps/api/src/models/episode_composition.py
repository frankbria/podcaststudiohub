"""EpisodeComposition model for final composition state"""

from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow


class EpisodeComposition(Base):
    """EpisodeComposition model for final composition state with snippet timeline"""

    __tablename__ = "episode_compositions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys (one composition per episode)
    episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    layout_id = Column(UUID(as_uuid=True), ForeignKey("episode_layouts.id", ondelete="SET NULL"), nullable=True, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Composition timeline
    # Structure (generated after merging):
    # [
    #   {
    #     "segment_type": "snippet",
    #     "snippet_id": "uuid",
    #     "snippet_name": "Intro Music",
    #     "start_time": 0.0,
    #     "end_time": 5.0,
    #     "duration": 5.0,
    #     "audio_source": "s3://bucket/snippets/intro.mp3"
    #   },
    #   {
    #     "segment_type": "main_content",
    #     "start_time": 5.0,
    #     "end_time": 305.0,
    #     "duration": 300.0,
    #     "audio_source": "generated_podcast.mp3"
    #   }
    # ]
    timeline = Column(JSONB, nullable=False, default=list)

    # Composition status: 'draft', 'preview', 'final'
    composition_status = Column(Text, nullable=False, default='draft', index=True)

    # Final composition file paths
    composed_file_path = Column(Text, nullable=True)
    composed_s3_key = Column(Text, nullable=True)
    composed_s3_url = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    episode = relationship("Episode")
    layout = relationship("EpisodeLayout")

    def __repr__(self) -> str:
        return f"<EpisodeComposition(id={self.id}, episode_id={self.episode_id}, status={self.composition_status})>"
