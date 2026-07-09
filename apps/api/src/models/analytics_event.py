"""Analytics event model for tracking user engagement"""

import hashlib
from sqlalchemy import Column, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow

VALID_EVENT_TYPES = {"download", "play", "share", "stream"}


class AnalyticsEvent(Base):
	"""Track individual user engagement events per episode/project"""

	__tablename__ = "analytics_events"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
	episode_id = Column(
		UUID(as_uuid=True),
		ForeignKey("episodes.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)
	project_id = Column(
		UUID(as_uuid=True),
		ForeignKey("projects.id", ondelete="CASCADE"),
		nullable=True,
		index=True,
	)

	# Event type: download, play, share, stream
	event_type = Column(Text, nullable=False, index=True)

	# Client context
	user_agent = Column(Text, nullable=True)
	referer = Column(Text, nullable=True)
	ip_address = Column(Text, nullable=True)  # SHA-256 hashed
	country = Column(Text, nullable=True)
	device_type = Column(Text, nullable=True)  # mobile, desktop, tablet, unknown
	app_name = Column(Text, nullable=True)  # Apple Podcasts, Spotify, etc.

	# Event metadata (renamed from metadata to avoid SQLAlchemy reserved name)
	event_metadata = Column("metadata", JSONB, nullable=True)

	created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

	episode = relationship("Episode", foreign_keys=[episode_id])
	project = relationship("Project", foreign_keys=[project_id])

	__table_args__ = (
		Index("ix_analytics_events_episode_created", "episode_id", "created_at"),
		Index("ix_analytics_events_project_created", "project_id", "created_at"),
	)

	def __repr__(self) -> str:
		return f"<AnalyticsEvent(id={self.id}, type={self.event_type}, episode={self.episode_id})>"


def hash_ip(ip: str) -> str:
	"""SHA-256 hash an IP address for privacy compliance."""
	return hashlib.sha256(ip.encode()).hexdigest()


def detect_device_type(user_agent: str) -> str:
	"""Detect device type from User-Agent string."""
	if not user_agent:
		return "unknown"
	ua_lower = user_agent.lower()
	if any(kw in ua_lower for kw in ("mobile", "android", "iphone", "ipod")):
		return "mobile"
	if any(kw in ua_lower for kw in ("tablet", "ipad")):
		return "tablet"
	if any(kw in ua_lower for kw in ("windows", "macintosh", "linux", "x11")):
		return "desktop"
	return "unknown"


def detect_app_name(user_agent: str) -> str:
	"""Detect podcast app from User-Agent string."""
	if not user_agent:
		return "unknown"
	ua_lower = user_agent.lower()
	if "apple podcasts" in ua_lower or "applecoremedia" in ua_lower:
		return "apple_podcasts"
	if "spotify" in ua_lower:
		return "spotify"
	if "overcast" in ua_lower:
		return "overcast"
	if "pocket casts" in ua_lower or "pocketcasts" in ua_lower:
		return "pocket_casts"
	if "castro" in ua_lower:
		return "castro"
	if "google podcasts" in ua_lower:
		return "google_podcasts"
	return "other"
