"""
Role-Based Access Control (RBAC) service.

Defines permissions for each team role and provides helpers
to check/assert whether a user has a specific permission within a team.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional

from ..models.team import TeamRole
from ..models.team_member import TeamMember


# ---------------------------------------------------------------------------
# Role → permission map
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
	TeamRole.OWNER: {
		"projects.create": True,
		"projects.edit": True,
		"projects.delete": True,
		"projects.read": True,
		"episodes.create": True,
		"episodes.edit": True,
		"episodes.delete": True,
		"episodes.publish": True,
		"episodes.read": True,
		"team.manage_members": True,
		"team.edit": True,
		"team.delete": True,
		"billing.manage": True,
		"billing.view": True,
		"analytics.view": True,
		"analytics.export": True,
	},
	TeamRole.EDITOR: {
		"projects.create": True,
		"projects.edit": True,
		"projects.delete": False,
		"projects.read": True,
		"episodes.create": True,
		"episodes.edit": True,
		"episodes.delete": False,
		"episodes.publish": True,
		"episodes.read": True,
		"team.manage_members": False,
		"team.edit": False,
		"team.delete": False,
		"billing.manage": False,
		"billing.view": False,
		"analytics.view": True,
		"analytics.export": False,
	},
	TeamRole.VIEWER: {
		"projects.create": False,
		"projects.edit": False,
		"projects.delete": False,
		"projects.read": True,
		"episodes.create": False,
		"episodes.edit": False,
		"episodes.delete": False,
		"episodes.publish": False,
		"episodes.read": True,
		"team.manage_members": False,
		"team.edit": False,
		"team.delete": False,
		"billing.manage": False,
		"billing.view": False,
		"analytics.view": False,
		"analytics.export": False,
	},
	TeamRole.ANALYST: {
		"projects.create": False,
		"projects.edit": False,
		"projects.delete": False,
		"projects.read": True,
		"episodes.create": False,
		"episodes.edit": False,
		"episodes.delete": False,
		"episodes.publish": False,
		"episodes.read": True,
		"team.manage_members": False,
		"team.edit": False,
		"team.delete": False,
		"billing.manage": False,
		"billing.view": False,
		"analytics.view": True,
		"analytics.export": True,
	},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_member(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
) -> Optional[TeamMember]:
	"""Return the TeamMember row for a user+team, or None."""
	result = await db.execute(
		select(TeamMember).where(
			TeamMember.user_id == user_id,
			TeamMember.team_id == team_id,
			TeamMember.status == "active",
		)
	)
	return result.scalar_one_or_none()


async def get_user_role(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
) -> Optional[str]:
	"""Return the user's role string in the given team, or None if not a member."""
	member = await get_member(db, user_id, team_id)
	return member.role if member else None


def role_has_permission(role: str, permission: str) -> bool:
	"""Return True if *role* grants *permission*."""
	perms = ROLE_PERMISSIONS.get(role, {})
	return perms.get(permission, False)


async def check_permission(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
	permission: str,
) -> bool:
	"""
	Return True if the user has the given permission in the team.

	Returns False if the user is not a member or the role does not grant
	the permission.
	"""
	role = await get_user_role(db, user_id, team_id)
	if role is None:
		return False
	return role_has_permission(role, permission)


async def assert_permission(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
	permission: str,
) -> None:
	"""
	Raise HTTP 403 if the user does not have the required permission.

	Raises HTTP 404 if the user is not a member of the team at all,
	to avoid leaking team existence to non-members.
	"""
	role = await get_user_role(db, user_id, team_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Team not found",
		)
	if not role_has_permission(role, permission):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail=f"Permission denied: {permission}",
		)
