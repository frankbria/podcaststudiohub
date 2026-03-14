"""TeamInvitation model for pending invitations to join a team"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from ..database import Base


class TeamInvitation(Base):
	"""Pending team invitations sent to email addresses"""

	__tablename__ = "team_invitations"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	team_id = Column(
		UUID(as_uuid=True),
		ForeignKey("teams.id", ondelete="CASCADE"),
		nullable=False,
		index=True
	)
	inviter_id = Column(
		UUID(as_uuid=True),
		ForeignKey("users.id"),
		nullable=False
	)

	# Target email and proposed role
	email = Column(String(255), nullable=False)
	role = Column(String(50), nullable=False, default="editor")

	# Unique token for accepting the invitation
	token = Column(String(255), unique=True, nullable=False, index=True)

	# Status: pending, accepted, declined, expired
	status = Column(String(50), nullable=False, default="pending")

	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	expires_at = Column(DateTime, nullable=False)
	accepted_at = Column(DateTime, nullable=True)

	# Relationships
	team = relationship("Team")
	inviter = relationship("User")

	def __repr__(self) -> str:
		return f"<TeamInvitation(team_id={self.team_id}, email={self.email}, status={self.status})>"
