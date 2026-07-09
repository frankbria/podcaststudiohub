"""TeamInvitation model for pending team invites"""

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow


class TeamInvitation(Base):
	"""Pending invitation for a user to join a team"""

	__tablename__ = "team_invitations"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	team_id = Column(
		UUID(as_uuid=True),
		ForeignKey("teams.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	inviter_id = Column(
		UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
	)

	# Invitee details
	email = Column(String(255), nullable=False)
	role = Column(String(50), nullable=False, default="editor")

	# Unique token for accepting the invitation
	token = Column(String(255), unique=True, nullable=False)

	# Status: pending, accepted, declined, expired
	status = Column(String(50), nullable=False, default="pending")

	# Timestamps
	created_at = Column(DateTime, default=utcnow, nullable=False)
	expires_at = Column(DateTime, nullable=False)
	accepted_at = Column(DateTime, nullable=True)

	# Relationships
	team = relationship("Team", back_populates="invitations")
	inviter = relationship("User")

	def __repr__(self) -> str:
		return f"<TeamInvitation(id={self.id}, email={self.email}, status={self.status})>"
