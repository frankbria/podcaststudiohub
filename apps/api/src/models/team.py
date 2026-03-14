"""Team model for group/organization management"""

from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

from ..database import Base


class TeamRole(str, Enum):
	"""Roles available within a team"""
	OWNER = "owner"
	EDITOR = "editor"
	VIEWER = "viewer"
	ANALYST = "analyst"


class Team(Base):
	"""Team or organization that groups users for collaboration"""

	__tablename__ = "teams"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String(255), nullable=False)
	description = Column(Text, nullable=True)
	logo_url = Column(Text, nullable=True)

	# Billing tier inherited from subscription
	tier = Column(String(50), default="free", nullable=False)
	stripe_customer_id = Column(String, unique=True, nullable=True)

	# Team-level settings (JSONB for flexibility)
	settings = Column(JSONB, nullable=True)

	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

	def __repr__(self) -> str:
		return f"<Team(id={self.id}, name={self.name})>"
