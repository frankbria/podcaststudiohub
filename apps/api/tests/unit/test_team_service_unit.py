"""
Direct service-layer unit tests for team_service.py.

These call the async service functions directly against a real AsyncSession
(the `test_db` fixture) instead of going through the router. Some branches
are unreachable through the API: every team route asserts membership via
`rbac_service.assert_permission` before calling into team_service, which
always returns 403 for a non-member — so team_service.get_team's own 404
for a nonexistent team, and similar not-found branches, can only be
exercised by calling the service layer directly.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.models.team_invitation import TeamInvitation
from src.models.team_member import TeamMember
from src.schemas.team import TeamCreate
from src.services import team_service
from tests.unit.conftest import _register_user
from src.utils.datetime_utils import utcnow


class TestGetTeamNotFound:
	@pytest.mark.asyncio
	async def test_raises_404_for_nonexistent_team(self, test_db):
		with pytest.raises(HTTPException) as exc:
			await team_service.get_team(test_db, uuid4())
		assert exc.value.status_code == 404


class TestUpdateTeamPartialUpdate:
	@pytest.mark.asyncio
	async def test_only_provided_fields_are_updated(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(
			test_db, owner_id, TeamCreate(name="Original Name", description="Original Description")
		)

		from src.schemas.team import TeamUpdate

		updated = await team_service.update_team(
			test_db, team.id, TeamUpdate(description="New Description")
		)
		assert updated.name == "Original Name"
		assert updated.description == "New Description"


class TestDeleteTeam:
	@pytest.mark.asyncio
	async def test_delete_team_removes_it(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Doomed Team"))

		await team_service.delete_team(test_db, team.id)

		with pytest.raises(HTTPException) as exc:
			await team_service.get_team(test_db, team.id)
		assert exc.value.status_code == 404


class TestGetMemberCount:
	@pytest.mark.asyncio
	async def test_counts_only_active_members(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Count Team"))
		assert await team_service.get_member_count(test_db, team.id) == 1

		other_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		test_db.add(TeamMember(team_id=team.id, user_id=other_id, role="viewer", status="suspended"))
		await test_db.commit()

		# Suspended members should not count.
		assert await team_service.get_member_count(test_db, team.id) == 1


class TestUpdateMemberRoleNotFound:
	@pytest.mark.asyncio
	async def test_raises_404_when_member_missing(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="No Member Team"))
		with pytest.raises(HTTPException) as exc:
			await team_service.update_member_role(test_db, team.id, uuid4(), "editor")
		assert exc.value.status_code == 404


class TestUpdateMemberRoleSuccess:
	@pytest.mark.asyncio
	async def test_changes_role_and_persists(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Role Team"))
		member_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		test_db.add(TeamMember(team_id=team.id, user_id=member_id, role="viewer", status="active"))
		await test_db.commit()

		updated = await team_service.update_member_role(test_db, team.id, member_id, "analyst")
		assert updated.role == "analyst"
		assert updated.user_id == member_id


class TestRemoveMemberNotFound:
	@pytest.mark.asyncio
	async def test_raises_404_when_member_missing(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="No Member Team 2"))
		with pytest.raises(HTTPException) as exc:
			await team_service.remove_member(test_db, team.id, uuid4())
		assert exc.value.status_code == 404


class TestRemoveMemberSuccess:
	@pytest.mark.asyncio
	async def test_removes_existing_member(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Removal Team"))
		member_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		test_db.add(TeamMember(team_id=team.id, user_id=member_id, role="viewer", status="active"))
		await test_db.commit()

		await team_service.remove_member(test_db, team.id, member_id)

		remaining = await team_service.get_members(test_db, team.id)
		assert member_id not in [m.user_id for m in remaining]


class TestAcceptInvitationExpired:
	@pytest.mark.asyncio
	async def test_expired_invitation_rejected_and_marked_expired(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		invitee_email = f"expired_{uuid4()}@example.com"
		invitee_id = await _register_user(client, invitee_email, full_name="Team Unit Test User")

		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Expired Invite Team"))

		token = "expired-token-" + uuid4().hex
		invitation = TeamInvitation(
			team_id=team.id,
			inviter_id=owner_id,
			email=invitee_email,
			role="viewer",
			token=token,
			status="pending",
			expires_at=utcnow() - timedelta(days=1),
		)
		test_db.add(invitation)
		await test_db.commit()

		with pytest.raises(HTTPException) as exc:
			await team_service.accept_invitation(test_db, token, invitee_id, invitee_email)
		assert exc.value.status_code == 400
		assert "expired" in exc.value.detail.lower()

		await test_db.refresh(invitation)
		assert invitation.status == "expired"


class TestAcceptInvitationAlreadyMember:
	@pytest.mark.asyncio
	async def test_already_member_rejected(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		member_email = f"already_{uuid4()}@example.com"
		member_id = await _register_user(client, member_email, full_name="Team Unit Test User")

		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Already Member Team"))

		# The invitee is already an active member of the team.
		test_db.add(TeamMember(team_id=team.id, user_id=member_id, role="viewer", status="active"))
		await test_db.commit()

		# A separate pending invitation exists for the same team/email.
		token = "already-token-" + uuid4().hex
		invitation = TeamInvitation(
			team_id=team.id,
			inviter_id=owner_id,
			email=member_email,
			role="viewer",
			token=token,
			status="pending",
			expires_at=utcnow() + timedelta(days=7),
		)
		test_db.add(invitation)
		await test_db.commit()

		with pytest.raises(HTTPException) as exc:
			await team_service.accept_invitation(test_db, token, member_id, member_email)
		assert exc.value.status_code == 400
		assert "already a member" in exc.value.detail.lower()


class TestAcceptInvitationSuccess:
	@pytest.mark.asyncio
	async def test_accept_creates_active_membership(self, test_db, client):
		owner_id = await _register_user(client, email_prefix="team_unit_", full_name="Team Unit Test User")
		invitee_email = f"accept_{uuid4()}@example.com"
		invitee_id = await _register_user(client, invitee_email, full_name="Team Unit Test User")

		team = await team_service.create_team(test_db, owner_id, TeamCreate(name="Accept Team"))

		token = "accept-token-" + uuid4().hex
		invitation = TeamInvitation(
			team_id=team.id,
			inviter_id=owner_id,
			email=invitee_email,
			role="editor",
			token=token,
			status="pending",
			expires_at=utcnow() + timedelta(days=7),
		)
		test_db.add(invitation)
		await test_db.commit()

		membership = await team_service.accept_invitation(test_db, token, invitee_id, invitee_email)
		assert membership.role == "editor"
		assert membership.status == "active"
		assert membership.user_id == invitee_id

		await test_db.refresh(invitation)
		assert invitation.status == "accepted"
		assert invitation.accepted_at is not None
