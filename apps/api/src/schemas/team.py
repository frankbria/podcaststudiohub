"""
Pydantic schemas for Team, TeamMember, and TeamInvitation endpoints.
"""

from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Team schemas
# ---------------------------------------------------------------------------


class TeamCreate(BaseModel):
	"""Schema for creating a new team."""

	name: str = Field(..., min_length=1, max_length=255)
	description: Optional[str] = None
	logo_url: Optional[str] = None


class TeamUpdate(BaseModel):
	"""Schema for partial team updates."""

	name: Optional[str] = Field(None, min_length=1, max_length=255)
	description: Optional[str] = None
	logo_url: Optional[str] = None


class TeamResponse(BaseModel):
	"""Schema for team response data."""

	id: UUID
	name: str
	description: Optional[str]
	logo_url: Optional[str]
	tier: str
	member_count: int = 0
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


class TeamListResponse(BaseModel):
	"""Schema for list of teams."""

	teams: list[TeamResponse]
	total: int


# ---------------------------------------------------------------------------
# Team member schemas
# ---------------------------------------------------------------------------


class TeamMemberResponse(BaseModel):
	"""Schema for a single team member entry."""

	id: UUID
	team_id: UUID
	user_id: UUID
	role: str
	status: str
	joined_at: datetime
	invited_at: Optional[datetime]
	last_activity: Optional[datetime]

	model_config = {"from_attributes": True}


class TeamMemberUpdate(BaseModel):
	"""Schema for updating a team member's role."""

	role: str = Field(..., pattern="^(owner|editor|viewer|analyst)$")


# ---------------------------------------------------------------------------
# Invitation schemas
# ---------------------------------------------------------------------------


class InvitationCreate(BaseModel):
	"""Schema for sending an invitation."""

	email: EmailStr
	role: str = Field("editor", pattern="^(owner|editor|viewer|analyst)$")


class InvitationResponse(BaseModel):
	"""Schema for invitation response data."""

	id: UUID
	team_id: UUID
	inviter_id: UUID
	email: str
	role: str
	status: str
	token: str
	created_at: datetime
	expires_at: datetime
	accepted_at: Optional[datetime]

	model_config = {"from_attributes": True}
