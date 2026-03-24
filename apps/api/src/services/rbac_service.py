"""
Role-Based Access Control (RBAC) service.

Defines permission matrices per role and provides helpers to check whether
a user holds a specific permission within a team.
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.team_member import TeamMember


# ---------------------------------------------------------------------------
# Role permission matrix
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
	"owner": {
		"projects.create": True,
		"projects.read": True,
		"projects.edit": True,
		"projects.delete": True,
		"episodes.create": True,
		"episodes.read": True,
		"episodes.edit": True,
		"episodes.delete": True,
		"episodes.publish": True,
		"team.edit": True,
		"team.manage_members": True,
		"team.delete": True,
		"billing.manage": True,
		"billing.view": True,
		"analytics.view": True,
		"analytics.export": True,
	},
	"editor": {
		"projects.create": True,
		"projects.read": True,
		"projects.edit": True,
		"projects.delete": False,
		"episodes.create": True,
		"episodes.read": True,
		"episodes.edit": True,
		"episodes.delete": False,
		"episodes.publish": True,
		"team.edit": False,
		"team.manage_members": False,
		"team.delete": False,
		"billing.manage": False,
		"billing.view": False,
		"analytics.view": True,
		"analytics.export": False,
	},
	"viewer": {
		"projects.create": False,
		"projects.read": True,
		"projects.edit": False,
		"projects.delete": False,
		"episodes.create": False,
		"episodes.read": True,
		"episodes.edit": False,
		"episodes.delete": False,
		"episodes.publish": False,
		"team.edit": False,
		"team.manage_members": False,
		"team.delete": False,
		"billing.manage": False,
		"billing.view": False,
		"analytics.view": True,
		"analytics.export": False,
	},
	"analyst": {
		"projects.create": False,
		"projects.read": True,
		"projects.edit": False,
		"projects.delete": False,
		"episodes.create": False,
		"episodes.read": True,
		"episodes.edit": False,
		"episodes.delete": False,
		"episodes.publish": False,
		"team.edit": False,
		"team.manage_members": False,
		"team.delete": False,
		"billing.manage": False,
		"billing.view": True,
		"analytics.view": True,
		"analytics.export": True,
	},
}


def role_has_permission(role: str, permission: str) -> bool:
	"""Return True if the given role includes the permission."""
	perms = ROLE_PERMISSIONS.get(role, {})
	return perms.get(permission, False)


async def get_membership(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
) -> Optional[TeamMember]:
	"""Return the TeamMember record for a user in a team, or None."""
	result = await db.execute(
		select(TeamMember).where(
			TeamMember.team_id == team_id,
			TeamMember.user_id == user_id,
			TeamMember.status == "active",
		)
	)
	return result.scalar_one_or_none()


async def get_user_role(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
) -> Optional[str]:
	"""Return user's role string in the team, or None if not a member."""
	membership = await get_membership(db, user_id, team_id)
	return membership.role if membership else None


async def check_permission(
	db: AsyncSession,
	user_id: UUID,
	team_id: UUID,
	permission: str,
) -> bool:
	"""Return True if the user has the requested permission in the team."""
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
	"""Raise HTTP 403 if the user lacks the requested permission."""
	has_perm = await check_permission(db, user_id, team_id, permission)
	if not has_perm:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail=f"Permission denied: {permission}",
		)
