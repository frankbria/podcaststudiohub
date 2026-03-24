"""TeamMember model for associating users with teams"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class TeamMember(Base):
	"""Team membership record with role assignment"""

	__tablename__ = "team_members"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	team_id = Column(
		UUID(as_uuid=True),
		ForeignKey("teams.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	user_id = Column(
		UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)

	# Role: owner, editor, viewer, analyst
	role = Column(String(50), nullable=False, default="viewer")

	# Optional per-member permission overrides
	permissions = Column(JSONB, nullable=True)

	# Status: active, pending, suspended
	status = Column(String(50), nullable=False, default="active")

	# Timestamps
	joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	invited_at = Column(DateTime, nullable=True)
	last_activity = Column(DateTime, nullable=True)

	# Relationships
	team = relationship("Team", back_populates="members")
	user = relationship("User")

	__table_args__ = (
		UniqueConstraint("team_id", "user_id", name="uq_team_user"),
	)

	def __repr__(self) -> str:
		return f"<TeamMember(team_id={self.team_id}, user_id={self.user_id}, role={self.role})>"
