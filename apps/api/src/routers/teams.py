"""
Team router for RESTful API endpoints.

Provides CRUD operations for teams, member management, and invitation flows.
All endpoints require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.team import (
	TeamCreate,
	TeamUpdate,
	TeamResponse,
	TeamListResponse,
	TeamMemberResponse,
	TeamMemberListResponse,
	TeamMemberUpdateRole,
	InvitationCreate,
	InvitationResponse,
	InvitationListResponse,
	UserSummary,
)
from ..services import team_service, rbac_service

router = APIRouter(prefix="/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build_team_response(team, member_count: int) -> TeamResponse:
	return TeamResponse(
		id=team.id,
		name=team.name,
		description=team.description,
		logo_url=team.logo_url,
		tier=team.tier,
		member_count=member_count,
		created_at=team.created_at,
		updated_at=team.updated_at,
	)


def _build_member_response(member) -> TeamMemberResponse:
	user_summary = None
	if member.user:
		user_summary = UserSummary(
			id=member.user.id,
			email=member.user.email,
			full_name=member.user.full_name,
		)
	return TeamMemberResponse(
		id=member.id,
		team_id=member.team_id,
		user_id=member.user_id,
		role=member.role,
		status=member.status,
		joined_at=member.joined_at,
		last_activity=member.last_activity,
		user=user_summary,
	)


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
	team_data: TeamCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create a new team.

	The authenticated user becomes the team owner automatically.
	"""
	team = await team_service.create_team(
		db=db,
		owner_id=current_user.id,
		team_data=team_data,
	)
	return _build_team_response(team, member_count=1)


@router.get("", response_model=TeamListResponse)
async def list_teams(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""List all teams the authenticated user belongs to."""
	teams = await team_service.get_user_teams(db=db, user_id=current_user.id)
	responses = []
	for team in teams:
		count = await team_service.get_member_count(db=db, team_id=team.id)
		responses.append(_build_team_response(team, member_count=count))
	return TeamListResponse(teams=responses, total=len(responses))


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get team details. User must be a member."""
	# Assert membership (raises 404 if not a member)
	await rbac_service.assert_permission(db, current_user.id, team_id, "projects.read")

	team = await team_service.get_team(db=db, team_id=team_id)
	if team is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

	count = await team_service.get_member_count(db=db, team_id=team_id)
	return _build_team_response(team, member_count=count)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
	team_id: UUID,
	update_data: TeamUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Update team metadata. Requires team.edit permission (owner)."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.edit")

	team = await team_service.get_team(db=db, team_id=team_id)
	if team is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

	updated = await team_service.update_team(db=db, team=team, update_data=update_data)
	count = await team_service.get_member_count(db=db, team_id=team_id)
	return _build_team_response(updated, member_count=count)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Delete a team and all associated data. Requires team.delete permission (owner)."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.delete")

	team = await team_service.get_team(db=db, team_id=team_id)
	if team is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

	await team_service.delete_team(db=db, team=team)
	return None


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

@router.get("/{team_id}/members", response_model=TeamMemberListResponse)
async def list_members(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""List team members. User must be a member."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "projects.read")

	members = await team_service.get_team_members(db=db, team_id=team_id)
	return TeamMemberListResponse(
		members=[_build_member_response(m) for m in members],
		total=len(members),
	)


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
async def update_member_role(
	team_id: UUID,
	user_id: UUID,
	role_data: TeamMemberUpdateRole,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Update a team member's role. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")

	member = await team_service.update_member_role(
		db=db,
		team_id=team_id,
		user_id=user_id,
		new_role=role_data.role,
	)
	return _build_member_response(member)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
	team_id: UUID,
	user_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Remove a member from a team. Requires team.manage_members permission."""
	# Allow members to remove themselves; otherwise require manage_members
	if current_user.id != user_id:
		await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")
	else:
		# Verify the user is at least a member
		await rbac_service.assert_permission(db, current_user.id, team_id, "projects.read")

	await team_service.remove_member(db=db, team_id=team_id, user_id=user_id)
	return None


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

@router.post("/{team_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
	team_id: UUID,
	invitation_data: InvitationCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Send an invitation to join the team. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")

	team = await team_service.get_team(db=db, team_id=team_id)
	if team is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

	invitation = await team_service.create_invitation(
		db=db,
		team_id=team_id,
		inviter_id=current_user.id,
		invitation_data=invitation_data,
	)
	return invitation


@router.get("/{team_id}/invitations", response_model=InvitationListResponse)
async def list_invitations(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""List pending invitations. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")

	invitations = await team_service.get_team_invitations(db=db, team_id=team_id)
	return InvitationListResponse(invitations=invitations, total=len(invitations))


@router.post("/invitations/{token}/accept", response_model=TeamMemberResponse)
async def accept_invitation(
	token: str,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Accept an invitation token and join the team."""
	member = await team_service.accept_invitation(
		db=db,
		token=token,
		user_id=current_user.id,
	)
	return _build_member_response(member)
