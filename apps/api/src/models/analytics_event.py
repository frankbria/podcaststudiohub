"""Analytics event model for tracking user engagement events"""

import hashlib
from datetime import datetime
import uuid

from sqlalchemy import Column, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from ..database import Base


class AnalyticsEvent(Base):
	"""Track individual user engagement events (downloads, plays, shares, streams)"""

	__tablename__ = "analytics_events"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	tenant_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
	episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True, index=True)
	project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)

	# Event type: 'download', 'play', 'share', 'stream'
	event_type = Column(Text, nullable=False, index=True)

	# Client context (no PII stored)
	user_agent = Column(Text, nullable=True)
	referer = Column(Text, nullable=True)
	ip_hash = Column(Text, nullable=True)  # SHA-256 hash of IP - not reversible
	country = Column(Text, nullable=True)
	device_type = Column(Text, nullable=True)  # 'mobile', 'desktop', 'tablet', 'unknown'
	app_name = Column(Text, nullable=True)  # Podcast app (Apple Podcasts, Spotify, etc.)

	# Event metadata
	event_metadata = Column("metadata", JSONB, nullable=True)  # {duration_listened: 120, completed: false, etc}

	created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

	episode = relationship("Episode")
	project = relationship("Project")

	__table_args__ = (
		Index('idx_analytics_events_episode_created', 'episode_id', 'created_at'),
		Index('idx_analytics_events_project_created', 'project_id', 'created_at'),
	)

	@staticmethod
	def hash_ip(ip_address: str) -> str:
		"""Hash IP address with SHA-256 for privacy compliance."""
		return hashlib.sha256(ip_address.encode()).hexdigest()

	def __repr__(self) -> str:
		return f"<AnalyticsEvent(id={self.id}, type={self.event_type}, episode_id={self.episode_id})>"
