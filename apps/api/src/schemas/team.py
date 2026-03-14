"""
Team schemas for request/response validation.

Defines Pydantic models for Team CRUD operations, member management,
and invitation flows.
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List


# ---------------------------------------------------------------------------
# Team schemas
# ---------------------------------------------------------------------------

class TeamCreate(BaseModel):
	"""Schema for creating a new team."""

	name: str = Field(..., min_length=1, max_length=255, description="Team name")
	description: Optional[str] = Field(None, description="Team description")


class TeamUpdate(BaseModel):
	"""Schema for updating team metadata. All fields optional."""

	name: Optional[str] = Field(None, min_length=1, max_length=255, description="Team name")
	description: Optional[str] = Field(None, description="Team description")
	logo_url: Optional[str] = Field(None, description="Logo URL")


class TeamResponse(BaseModel):
	"""Schema for team response data."""

	id: UUID
	name: str
	description: Optional[str]
	logo_url: Optional[str]
	tier: str
	member_count: int = Field(default=0, description="Number of active members")
	created_at: datetime
	updated_at: datetime

	model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Team member schemas
# ---------------------------------------------------------------------------

class UserSummary(BaseModel):
	"""Minimal user info embedded in member responses."""

	id: UUID
	email: str
	full_name: Optional[str]

	model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
	"""Schema for team member response."""

	id: UUID
	team_id: UUID
	user_id: UUID
	role: str
	status: str
	joined_at: datetime
	last_activity: Optional[datetime]
	user: Optional[UserSummary] = None

	model_config = {"from_attributes": True}


class TeamMemberUpdateRole(BaseModel):
	"""Schema for updating a team member's role."""

	role: str = Field(..., description="New role: owner, editor, viewer, analyst")


# ---------------------------------------------------------------------------
# Invitation schemas
# ---------------------------------------------------------------------------

class InvitationCreate(BaseModel):
	"""Schema for creating a new team invitation."""

	email: str = Field(..., description="Email address to invite")
	role: str = Field(default="editor", description="Role: owner, editor, viewer, analyst")


class InvitationResponse(BaseModel):
	"""Schema for invitation response."""

	id: UUID
	team_id: UUID
	inviter_id: UUID
	email: str
	role: str
	token: str
	status: str
	created_at: datetime
	expires_at: datetime
	accepted_at: Optional[datetime]

	model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# List responses
# ---------------------------------------------------------------------------

class TeamListResponse(BaseModel):
	"""Schema for paginated list of teams."""

	teams: List[TeamResponse]
	total: int


class TeamMemberListResponse(BaseModel):
	"""Schema for list of team members."""

	members: List[TeamMemberResponse]
	total: int


class InvitationListResponse(BaseModel):
	"""Schema for list of pending invitations."""

	invitations: List[InvitationResponse]
	total: int
