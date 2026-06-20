"""
Teams router: team management, membership, and invitation endpoints.
"""

from fastapi import APIRouter, Depends, status
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
	TeamMemberUpdate,
	InvitationCreate,
	InvitationResponse,
)
from ..services import team_service, rbac_service

router = APIRouter(prefix="/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Helper: build TeamResponse with member_count
# ---------------------------------------------------------------------------


async def _team_response(team, db: AsyncSession) -> TeamResponse:
	count = await team_service.get_member_count(db, team.id)
	data = TeamResponse.model_validate(team)
	data.member_count = count
	return data


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
	team_data: TeamCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Create a new team. The caller becomes the owner."""
	team = await team_service.create_team(db, current_user.id, team_data)
	return await _team_response(team, db)


@router.get("", response_model=TeamListResponse)
async def list_teams(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""List all teams the current user belongs to."""
	teams = await team_service.get_teams_for_user(db, current_user.id)
	team_responses = [await _team_response(t, db) for t in teams]
	return TeamListResponse(teams=team_responses, total=len(team_responses))


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get team details. Caller must be a member."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "projects.read")
	team = await team_service.get_team(db, team_id)
	return await _team_response(team, db)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
	team_id: UUID,
	team_data: TeamUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Update team metadata. Requires team.edit permission (owner only)."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.edit")
	team = await team_service.update_team(db, team_id, team_data)
	return await _team_response(team, db)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Delete team and all data. Requires team.delete permission (owner only)."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.delete")
	await team_service.delete_team(db, team_id)


# ---------------------------------------------------------------------------
# Membership endpoints
# ---------------------------------------------------------------------------


@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_members(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""List team members. Caller must be a member."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "projects.read")
	return await team_service.get_members(db, team_id)


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
async def update_member_role(
	team_id: UUID,
	user_id: UUID,
	data: TeamMemberUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Update a member's role. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")
	return await team_service.update_member_role(db, team_id, user_id, data.role)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
	team_id: UUID,
	user_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Remove a member from the team. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")
	await team_service.remove_member(db, team_id, user_id)


# ---------------------------------------------------------------------------
# Invitation endpoints
# ---------------------------------------------------------------------------


@router.post("/{team_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
	team_id: UUID,
	invite_data: InvitationCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Send invitation to join a team. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")
	return await team_service.create_invitation(db, team_id, current_user.id, invite_data)


@router.get("/{team_id}/invitations", response_model=list[InvitationResponse])
async def list_invitations(
	team_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""List pending invitations for a team. Requires team.manage_members permission."""
	await rbac_service.assert_permission(db, current_user.id, team_id, "team.manage_members")
	return await team_service.get_invitations(db, team_id)


@router.post("/invitations/{token}/accept", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def accept_invitation(
	token: str,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Accept an invitation token and join the team.

	The invitation is bound to the invited email: a user whose email does not
	match the invitation is rejected (403), so a forwarded token cannot be used.
	"""
	return await team_service.accept_invitation(db, token, current_user.id, current_user.email)
