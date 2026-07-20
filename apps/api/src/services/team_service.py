"""
Team service: business logic for team CRUD, memberships, and invitations.

Security note — team tables are intentionally NOT row-level-security (RLS)
scoped. `teams`, `team_members`, and `team_invitations` have no `tenant_id`
column: a team is a shared, cross-user resource rather than data owned by a
single tenant, so the per-tenant RLS policies applied in migration 003 do not
apply to them (see migration 009). Isolation for these tables is enforced at
the application layer via RBAC — every team route asserts membership/permission
through `rbac_service.assert_permission`. Any new team route MUST do the same.
"""

import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.team import Team
from ..models.team_member import TeamMember
from ..models.team_invitation import TeamInvitation
from ..schemas.team import TeamCreate, TeamUpdate, InvitationCreate
from ..utils.datetime_utils import utcnow

# Roles that may be granted through an invitation. `owner` is excluded: an
# invitation token is forwardable, so granting ownership through it is a
# privilege-escalation vector (ownership is granted via update_member_role).
# Enforced at acceptance as well as creation so tokens issued before the role
# restriction was deployed cannot still grant a disallowed role.
INVITABLE_ROLES = frozenset({"editor", "viewer", "analyst"})


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------


async def create_team(
	db: AsyncSession,
	owner_id: UUID,
	team_data: TeamCreate,
) -> Team:
	"""Create a new team and add the creator as owner."""
	team = Team(
		name=team_data.name,
		description=team_data.description,
		logo_url=team_data.logo_url,
	)
	db.add(team)
	await db.flush()  # obtain team.id before creating membership

	membership = TeamMember(
		team_id=team.id,
		user_id=owner_id,
		role="owner",
		status="active",
	)
	db.add(membership)
	await db.commit()
	await db.refresh(team)
	return team


async def get_team(db: AsyncSession, team_id: UUID) -> Team:
	"""Return team by ID or raise 404."""
	result = await db.execute(select(Team).where(Team.id == team_id))
	team = result.scalar_one_or_none()
	if team is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
	return team


async def get_teams_for_user(
	db: AsyncSession,
	user_id: UUID,
	limit: int | None = None,
	offset: int = 0,
) -> list[Team]:
	"""Return teams the user is an active member of, ordered by creation.

	When ``limit`` is given the result is a single page (with ``offset``); the
	list endpoint uses this to cap response size. ``count_teams_for_user`` gives
	the unpaginated total.
	"""
	query = (
		select(Team)
		.join(TeamMember, TeamMember.team_id == Team.id)
		.where(TeamMember.user_id == user_id, TeamMember.status == "active")
		.order_by(Team.created_at)
	)
	if offset:
		query = query.offset(offset)
	if limit is not None:
		query = query.limit(limit)
	result = await db.execute(query)
	return list(result.scalars().all())


async def count_teams_for_user(db: AsyncSession, user_id: UUID) -> int:
	"""Count all teams the user is an active member of (pagination total)."""
	result = await db.execute(
		select(func.count())
		.select_from(Team)
		.join(TeamMember, TeamMember.team_id == Team.id)
		.where(TeamMember.user_id == user_id, TeamMember.status == "active")
	)
	return result.scalar_one() or 0


async def update_team(
	db: AsyncSession,
	team_id: UUID,
	team_data: TeamUpdate,
) -> Team:
	"""Update team metadata fields."""
	team = await get_team(db, team_id)
	update_data = team_data.model_dump(exclude_unset=True)
	for field, value in update_data.items():
		setattr(team, field, value)
	team.updated_at = utcnow()
	await db.commit()
	await db.refresh(team)
	return team


async def delete_team(db: AsyncSession, team_id: UUID) -> None:
	"""Delete a team and all cascade-deleted records."""
	team = await get_team(db, team_id)
	await db.delete(team)
	await db.commit()


async def get_member_count(db: AsyncSession, team_id: UUID) -> int:
	"""Return count of active members in team (single team)."""
	result = await db.execute(
		select(func.count(TeamMember.id)).where(
			TeamMember.team_id == team_id,
			TeamMember.status == "active",
		)
	)
	return result.scalar_one() or 0


async def get_member_counts(
	db: AsyncSession, team_ids: list[UUID]
) -> dict[UUID, int]:
	"""Return active-member counts for many teams in one grouped query.

	Replaces the N+1 loop of per-team ``get_member_count`` calls in list
	endpoints. Teams with zero active members are absent from the dict
	(callers default to 0).
	"""
	if not team_ids:
		return {}
	result = await db.execute(
		select(TeamMember.team_id, func.count(TeamMember.id))
		.where(
			TeamMember.team_id.in_(team_ids),
			TeamMember.status == "active",
		)
		.group_by(TeamMember.team_id)
	)
	return {team_id: count for team_id, count in result.all()}


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


async def get_members(db: AsyncSession, team_id: UUID) -> list[TeamMember]:
	"""Return all active team members."""
	result = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == team_id,
			TeamMember.status == "active",
		).order_by(TeamMember.joined_at)
	)
	return list(result.scalars().all())


async def update_member_role(
	db: AsyncSession,
	team_id: UUID,
	user_id: UUID,
	new_role: str,
) -> TeamMember:
	"""Change a team member's role."""
	result = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == team_id,
			TeamMember.user_id == user_id,
		)
	)
	member = result.scalar_one_or_none()
	if member is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
	member.role = new_role
	await db.commit()
	await db.refresh(member)
	return member


async def remove_member(
	db: AsyncSession,
	team_id: UUID,
	user_id: UUID,
) -> None:
	"""Remove a member from the team."""
	result = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == team_id,
			TeamMember.user_id == user_id,
		)
	)
	member = result.scalar_one_or_none()
	if member is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
	await db.delete(member)
	await db.commit()


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


async def create_invitation(
	db: AsyncSession,
	team_id: UUID,
	inviter_id: UUID,
	invite_data: InvitationCreate,
	expires_in_days: int = 7,
) -> TeamInvitation:
	"""Create and store a new team invitation with a secure token."""
	token = secrets.token_urlsafe(32)
	invitation = TeamInvitation(
		team_id=team_id,
		inviter_id=inviter_id,
		email=invite_data.email,
		role=invite_data.role,
		token=token,
		status="pending",
		expires_at=utcnow() + timedelta(days=expires_in_days),
	)
	db.add(invitation)
	await db.commit()
	await db.refresh(invitation)
	return invitation


async def get_invitations(db: AsyncSession, team_id: UUID) -> list[TeamInvitation]:
	"""Return all pending invitations for a team."""
	result = await db.execute(
		select(TeamInvitation).where(
			TeamInvitation.team_id == team_id,
			TeamInvitation.status == "pending",
		).order_by(TeamInvitation.created_at)
	)
	return list(result.scalars().all())


async def accept_invitation(
	db: AsyncSession,
	token: str,
	user_id: UUID,
	user_email: str,
) -> TeamMember:
	"""Accept an invitation token and create a TeamMember record.

	The accepting user's email must match the invited email, otherwise a
	forwarded/leaked token would let any user join. The match is case-insensitive:
	account emails are now canonicalized to lowercase at rest (#255), so case is
	never identity-significant and a case-variant cannot be a distinct account.
	Membership is created with the invitation's role.
	"""
	result = await db.execute(
		select(TeamInvitation).where(TeamInvitation.token == token)
	)
	invitation = result.scalar_one_or_none()
	if invitation is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
	if invitation.email.lower() != user_email.lower():
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="This invitation was sent to a different email address",
		)
	if invitation.role not in INVITABLE_ROLES:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="This invitation grants a role that can no longer be accepted",
		)
	if invitation.status != "pending":
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invitation is {invitation.status}",
		)
	if invitation.expires_at < utcnow():
		invitation.status = "expired"
		await db.commit()
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired")

	# Check if already a member
	existing = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == invitation.team_id,
			TeamMember.user_id == user_id,
		)
	)
	if existing.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Already a member of this team",
		)

	# Create membership
	membership = TeamMember(
		team_id=invitation.team_id,
		user_id=user_id,
		role=invitation.role,
		status="active",
		invited_at=invitation.created_at,
	)
	db.add(membership)

	# Mark invitation accepted
	invitation.status = "accepted"
	invitation.accepted_at = utcnow()
	await db.commit()
	await db.refresh(membership)
	return membership
