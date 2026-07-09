"""Team model for group collaboration"""

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow


class Team(Base):
	"""Team or organization for collaborative podcast production"""

	__tablename__ = "teams"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String(255), nullable=False)
	description = Column(Text, nullable=True)
	logo_url = Column(Text, nullable=True)

	# Tier inherited from subscription billing
	tier = Column(String(50), default="free", nullable=False)
	stripe_customer_id = Column(String(255), unique=True, nullable=True)

	# Team-level settings (JSONB)
	settings = Column(JSONB, nullable=True)

	# Timestamps
	created_at = Column(DateTime, default=utcnow, nullable=False)
	updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

	# Relationships
	members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
	invitations = relationship("TeamInvitation", back_populates="team", cascade="all, delete-orphan")

	def __repr__(self) -> str:
		return f"<Team(id={self.id}, name={self.name})>"
