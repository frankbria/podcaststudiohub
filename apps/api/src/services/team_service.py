"""
Team service layer for business logic.

Provides operations for creating/managing teams, memberships, and invitations.
"""

import secrets
from datetime import datetime, timedelta
from uuid import UUID
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.team import Team, TeamRole
from ..models.team_member import TeamMember
from ..models.team_invitation import TeamInvitation
from ..schemas.team import TeamCreate, TeamUpdate, InvitationCreate


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------

async def create_team(
	db: AsyncSession,
	owner_id: UUID,
	team_data: TeamCreate,
) -> Team:
	"""
	Create a new team and add the creator as the owner.

	Args:
		db: Database session
		owner_id: ID of the user creating the team (becomes owner)
		team_data: Team creation data

	Returns:
		Created Team instance
	"""
	team = Team(
		name=team_data.name,
		description=team_data.description,
	)
	db.add(team)
	await db.flush()  # Get the team ID before adding the member

	# Add creator as owner
	member = TeamMember(
		team_id=team.id,
		user_id=owner_id,
		role=TeamRole.OWNER,
		status="active",
		joined_at=datetime.utcnow(),
	)
	db.add(member)
	await db.commit()
	return team


async def get_team(db: AsyncSession, team_id: UUID) -> Optional[Team]:
	"""Get team by ID."""
	result = await db.execute(select(Team).where(Team.id == team_id))
	return result.scalar_one_or_none()


async def get_user_teams(db: AsyncSession, user_id: UUID) -> list[Team]:
	"""Return all teams that the user is an active member of."""
	result = await db.execute(
		select(Team)
		.join(TeamMember, TeamMember.team_id == Team.id)
		.where(TeamMember.user_id == user_id, TeamMember.status == "active")
		.order_by(Team.created_at.desc())
	)
	return list(result.scalars().all())


async def update_team(
	db: AsyncSession,
	team: Team,
	update_data: TeamUpdate,
) -> Team:
	"""Update team metadata."""
	update_dict = update_data.model_dump(exclude_unset=True)
	for field, value in update_dict.items():
		setattr(team, field, value)
	await db.commit()
	return team


async def delete_team(db: AsyncSession, team: Team) -> None:
	"""Delete a team and all cascade-related records."""
	await db.delete(team)
	await db.commit()


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

async def get_team_members(db: AsyncSession, team_id: UUID) -> list[TeamMember]:
	"""Return active members of a team, with their user relationship loaded."""
	from sqlalchemy.orm import selectinload
	result = await db.execute(
		select(TeamMember)
		.options(selectinload(TeamMember.user))
		.where(TeamMember.team_id == team_id, TeamMember.status == "active")
		.order_by(TeamMember.joined_at)
	)
	return list(result.scalars().all())


async def get_member_count(db: AsyncSession, team_id: UUID) -> int:
	"""Return count of active members in a team."""
	result = await db.execute(
		select(func.count(TeamMember.id)).where(
			TeamMember.team_id == team_id,
			TeamMember.status == "active",
		)
	)
	return result.scalar() or 0


async def remove_member(
	db: AsyncSession,
	team_id: UUID,
	user_id: UUID,
) -> None:
	"""
	Remove a user from a team.

	Raises 404 if the membership does not exist, 400 if trying to remove
	the last owner.
	"""
	result = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == team_id,
			TeamMember.user_id == user_id,
		)
	)
	member = result.scalar_one_or_none()
	if member is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Team member not found",
		)

	# Prevent removing the last owner
	if member.role == TeamRole.OWNER:
		owner_count_result = await db.execute(
			select(func.count(TeamMember.id)).where(
				TeamMember.team_id == team_id,
				TeamMember.role == TeamRole.OWNER,
				TeamMember.status == "active",
			)
		)
		if (owner_count_result.scalar() or 0) <= 1:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Cannot remove the last owner from a team",
			)

	await db.delete(member)
	await db.commit()


async def update_member_role(
	db: AsyncSession,
	team_id: UUID,
	user_id: UUID,
	new_role: str,
) -> TeamMember:
	"""
	Change a team member's role.

	Raises 400 if new_role is not a valid TeamRole value.
	Raises 400 if downgrading the last owner.
	"""
	if new_role not in [r.value for r in TeamRole]:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid role: {new_role}. Valid values: {[r.value for r in TeamRole]}",
		)

	result = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == team_id,
			TeamMember.user_id == user_id,
		)
	)
	member = result.scalar_one_or_none()
	if member is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Team member not found",
		)

	# Prevent removing the last owner via role change
	if member.role == TeamRole.OWNER and new_role != TeamRole.OWNER:
		owner_count_result = await db.execute(
			select(func.count(TeamMember.id)).where(
				TeamMember.team_id == team_id,
				TeamMember.role == TeamRole.OWNER,
				TeamMember.status == "active",
			)
		)
		if (owner_count_result.scalar() or 0) <= 1:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Cannot change role of the last owner",
			)

	member.role = new_role
	await db.commit()
	return member


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

INVITATION_TTL_DAYS = 7


async def create_invitation(
	db: AsyncSession,
	team_id: UUID,
	inviter_id: UUID,
	invitation_data: InvitationCreate,
) -> TeamInvitation:
	"""
	Create an invitation for an email address to join the team.

	Raises 400 if the role is invalid.
	"""
	if invitation_data.role not in [r.value for r in TeamRole]:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid role: {invitation_data.role}",
		)

	token = secrets.token_urlsafe(32)
	invitation = TeamInvitation(
		team_id=team_id,
		inviter_id=inviter_id,
		email=invitation_data.email,
		role=invitation_data.role,
		token=token,
		status="pending",
		created_at=datetime.utcnow(),
		expires_at=datetime.utcnow() + timedelta(days=INVITATION_TTL_DAYS),
	)
	db.add(invitation)
	await db.commit()
	return invitation


async def get_team_invitations(
	db: AsyncSession,
	team_id: UUID,
) -> list[TeamInvitation]:
	"""Return all pending invitations for a team."""
	result = await db.execute(
		select(TeamInvitation).where(
			TeamInvitation.team_id == team_id,
			TeamInvitation.status == "pending",
		).order_by(TeamInvitation.created_at.desc())
	)
	return list(result.scalars().all())


async def accept_invitation(
	db: AsyncSession,
	token: str,
	user_id: UUID,
) -> TeamMember:
	"""
	Accept an invitation token and create a TeamMember record.

	Raises 404 if the token is unknown.
	Raises 400 if the invitation is expired or already accepted.
	"""
	result = await db.execute(
		select(TeamInvitation).where(TeamInvitation.token == token)
	)
	invitation = result.scalar_one_or_none()
	if invitation is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Invitation not found",
		)

	if invitation.status != "pending":
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invitation is already {invitation.status}",
		)

	if invitation.expires_at < datetime.utcnow():
		invitation.status = "expired"
		await db.commit()
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invitation has expired",
		)

	# Check if user is already a member
	existing = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == invitation.team_id,
			TeamMember.user_id == user_id,
		)
	)
	if existing.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="User is already a member of this team",
		)

	# Create member record
	now = datetime.utcnow()
	member = TeamMember(
		team_id=invitation.team_id,
		user_id=user_id,
		role=invitation.role,
		status="active",
		joined_at=now,
		invited_at=invitation.created_at,
	)
	db.add(member)

	# Mark invitation as accepted
	invitation.status = "accepted"
	invitation.accepted_at = now

	await db.commit()

	# Re-fetch member with user relationship eagerly loaded to avoid
	# async lazy-load errors when the caller accesses member.user.
	from sqlalchemy.orm import selectinload
	refreshed = await db.execute(
		select(TeamMember)
		.options(selectinload(TeamMember.user))
		.where(TeamMember.id == member.id)
	)
	return refreshed.scalar_one()
