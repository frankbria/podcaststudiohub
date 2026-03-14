"""
Test suite for Team Collaboration API (GAP-051).

Tests cover:
- Team CRUD
- Member management (list, update role, remove)
- Invitation flow (create, list, accept)
- RBAC: viewer/editor/owner permission enforcement
- Authentication requirements
"""

import pytest
from uuid import uuid4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _register_and_login(client, email: str = None, password: str = "SecurePass123!") -> dict:
	"""Register a user and return auth headers."""
	if email is None:
		email = f"user_{uuid4()}@example.com"
	resp = await client.post("/auth/register", json={
		"email": email,
		"password": password,
		"full_name": "Test User",
	})
	assert resp.status_code == 201, resp.text
	token = resp.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(client):
	return await _register_and_login(client)


@pytest.fixture
async def second_user_headers(client):
	return await _register_and_login(client)


@pytest.fixture
async def third_user_headers(client):
	return await _register_and_login(client)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_team(client, headers, name="Test Team", description=None):
	"""Create a team and return the response JSON."""
	payload = {"name": name}
	if description:
		payload["description"] = description
	resp = await client.post("/teams", headers=headers, json=payload)
	assert resp.status_code == 201, resp.text
	return resp.json()


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_team_requires_auth(client):
	resp = await client.post("/teams", json={"name": "No Auth Team"})
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_teams_requires_auth(client):
	resp = await client.get("/teams")
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_team_requires_auth(client):
	resp = await client.get(f"/teams/{uuid4()}")
	assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Team CRUD tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_team(client, auth_headers):
	"""Owner can create a team and is automatically added as owner."""
	resp = await client.post("/teams", headers=auth_headers, json={
		"name": "ACME Studios",
		"description": "A podcast studio",
	})
	assert resp.status_code == 201
	data = resp.json()
	assert data["name"] == "ACME Studios"
	assert data["description"] == "A podcast studio"
	assert data["tier"] == "free"
	assert data["member_count"] == 1
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_create_team_minimal(client, auth_headers):
	"""Team can be created with only a name."""
	resp = await client.post("/teams", headers=auth_headers, json={"name": "Solo Pod"})
	assert resp.status_code == 201
	assert resp.json()["name"] == "Solo Pod"
	assert resp.json()["description"] is None


@pytest.mark.asyncio
async def test_create_team_validates_name(client, auth_headers):
	"""Empty name is rejected."""
	resp = await client.post("/teams", headers=auth_headers, json={"name": ""})
	assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_teams_empty(client, auth_headers):
	"""A new user has no teams."""
	resp = await client.get("/teams", headers=auth_headers)
	assert resp.status_code == 200
	data = resp.json()
	assert data["total"] == 0
	assert data["teams"] == []


@pytest.mark.asyncio
async def test_list_teams(client, auth_headers):
	"""Teams user belongs to are returned."""
	await create_team(client, auth_headers, "Team A")
	await create_team(client, auth_headers, "Team B")

	resp = await client.get("/teams", headers=auth_headers)
	assert resp.status_code == 200
	data = resp.json()
	assert data["total"] == 2
	names = {t["name"] for t in data["teams"]}
	assert names == {"Team A", "Team B"}


@pytest.mark.asyncio
async def test_get_team(client, auth_headers):
	"""Team detail returned for a member."""
	team = await create_team(client, auth_headers, "Detail Team")
	resp = await client.get(f"/teams/{team['id']}", headers=auth_headers)
	assert resp.status_code == 200
	assert resp.json()["id"] == team["id"]
	assert resp.json()["name"] == "Detail Team"


@pytest.mark.asyncio
async def test_get_team_non_member(client, auth_headers, second_user_headers):
	"""Non-member gets 404 (not 403) to avoid leaking existence."""
	team = await create_team(client, auth_headers, "Private Team")
	resp = await client.get(f"/teams/{team['id']}", headers=second_user_headers)
	assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_team(client, auth_headers):
	"""Owner can update team metadata."""
	team = await create_team(client, auth_headers, "Old Name")
	resp = await client.patch(f"/teams/{team['id']}", headers=auth_headers, json={
		"name": "New Name",
		"description": "Updated",
	})
	assert resp.status_code == 200
	assert resp.json()["name"] == "New Name"
	assert resp.json()["description"] == "Updated"


@pytest.mark.asyncio
async def test_update_team_non_owner(client, auth_headers, second_user_headers):
	"""Non-owner cannot update team metadata."""
	team = await create_team(client, auth_headers, "Owner's Team")

	# Invite second user as viewer
	inv_resp = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "viewer@example.com",
		"role": "viewer",
	})
	assert inv_resp.status_code == 201
	token = inv_resp.json()["token"]

	# Accept invitation
	await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)

	# Attempt to update team
	resp = await client.patch(f"/teams/{team['id']}", headers=second_user_headers, json={"name": "Hacked"})
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_team(client, auth_headers):
	"""Owner can delete a team."""
	team = await create_team(client, auth_headers, "Doomed Team")
	resp = await client.delete(f"/teams/{team['id']}", headers=auth_headers)
	assert resp.status_code == 204

	# Team should no longer be visible
	get_resp = await client.get(f"/teams/{team['id']}", headers=auth_headers)
	assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_team_requires_owner(client, auth_headers, second_user_headers):
	"""Non-owner cannot delete a team."""
	team = await create_team(client, auth_headers, "Protected Team")

	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "editor@example.com",
		"role": "editor",
	})
	token = inv.json()["token"]
	await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)

	resp = await client.delete(f"/teams/{team['id']}", headers=second_user_headers)
	assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Member management tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_members(client, auth_headers):
	"""Owner can list team members."""
	team = await create_team(client, auth_headers, "Member Team")
	resp = await client.get(f"/teams/{team['id']}/members", headers=auth_headers)
	assert resp.status_code == 200
	data = resp.json()
	assert data["total"] == 1
	assert data["members"][0]["role"] == "owner"


@pytest.mark.asyncio
async def test_update_member_role(client, auth_headers, second_user_headers):
	"""Owner can change a member's role."""
	team = await create_team(client, auth_headers, "Role Team")

	# Invite second user as viewer
	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "member@example.com",
		"role": "viewer",
	})
	token = inv.json()["token"]
	accept = await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)
	assert accept.status_code == 200
	member_user_id = accept.json()["user_id"]

	# Promote to editor
	resp = await client.patch(
		f"/teams/{team['id']}/members/{member_user_id}",
		headers=auth_headers,
		json={"role": "editor"},
	)
	assert resp.status_code == 200
	assert resp.json()["role"] == "editor"


@pytest.mark.asyncio
async def test_update_member_role_invalid(client, auth_headers, second_user_headers):
	"""Invalid role returns 400."""
	team = await create_team(client, auth_headers, "Role Team 2")

	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "member2@example.com",
		"role": "viewer",
	})
	token = inv.json()["token"]
	accept = await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)
	member_user_id = accept.json()["user_id"]

	resp = await client.patch(
		f"/teams/{team['id']}/members/{member_user_id}",
		headers=auth_headers,
		json={"role": "superadmin"},
	)
	assert resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_member(client, auth_headers, second_user_headers):
	"""Owner can remove a member."""
	team = await create_team(client, auth_headers, "Remove Team")

	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "todelete@example.com",
		"role": "editor",
	})
	token = inv.json()["token"]
	accept = await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)
	member_user_id = accept.json()["user_id"]

	resp = await client.delete(
		f"/teams/{team['id']}/members/{member_user_id}",
		headers=auth_headers,
	)
	assert resp.status_code == 204

	# Member count back to 1
	members_resp = await client.get(f"/teams/{team['id']}/members", headers=auth_headers)
	assert members_resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_cannot_remove_last_owner(client, auth_headers):
	"""Cannot remove the only owner from a team."""
	team = await create_team(client, auth_headers, "Lone Owner Team")
	members_resp = await client.get(f"/teams/{team['id']}/members", headers=auth_headers)
	owner_user_id = members_resp.json()["members"][0]["user_id"]

	resp = await client.delete(
		f"/teams/{team['id']}/members/{owner_user_id}",
		headers=auth_headers,
	)
	assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Invitation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_invitation(client, auth_headers):
	"""Owner can create an invitation."""
	team = await create_team(client, auth_headers, "Invite Team")
	resp = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "newmember@example.com",
		"role": "editor",
	})
	assert resp.status_code == 201
	data = resp.json()
	assert data["email"] == "newmember@example.com"
	assert data["role"] == "editor"
	assert data["status"] == "pending"
	assert "token" in data
	assert "expires_at" in data


@pytest.mark.asyncio
async def test_create_invitation_invalid_role(client, auth_headers):
	"""Invitation with invalid role returns 400."""
	team = await create_team(client, auth_headers, "Bad Role Team")
	resp = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "x@example.com",
		"role": "god",
	})
	assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_invitations(client, auth_headers):
	"""Owner can list pending invitations."""
	team = await create_team(client, auth_headers, "List Invites Team")
	await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "a@example.com",
		"role": "viewer",
	})
	await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "b@example.com",
		"role": "editor",
	})

	resp = await client.get(f"/teams/{team['id']}/invitations", headers=auth_headers)
	assert resp.status_code == 200
	assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_accept_invitation(client, auth_headers, second_user_headers):
	"""A user can accept an invitation and becomes a team member."""
	team = await create_team(client, auth_headers, "Accept Team")
	inv_resp = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "joiner@example.com",
		"role": "editor",
	})
	token = inv_resp.json()["token"]

	accept_resp = await client.post(
		f"/teams/invitations/{token}/accept",
		headers=second_user_headers,
	)
	assert accept_resp.status_code == 200
	assert accept_resp.json()["role"] == "editor"
	assert accept_resp.json()["status"] == "active"

	# Member count should now be 2
	members = await client.get(f"/teams/{team['id']}/members", headers=auth_headers)
	assert members.json()["total"] == 2


@pytest.mark.asyncio
async def test_accept_nonexistent_invitation(client, auth_headers):
	"""Accepting a non-existent token returns 404."""
	resp = await client.post(
		"/teams/invitations/nonexistenttoken123/accept",
		headers=auth_headers,
	)
	assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_accept_invitation_twice(client, auth_headers, second_user_headers, third_user_headers):
	"""An already-accepted invitation cannot be accepted again."""
	team = await create_team(client, auth_headers, "Double Accept Team")
	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "joiner@example.com",
		"role": "viewer",
	})
	token = inv.json()["token"]

	# Accept once
	await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)

	# Try to accept again with a different user
	resp = await client.post(f"/teams/invitations/{token}/accept", headers=third_user_headers)
	assert resp.status_code == 400


@pytest.mark.asyncio
async def test_viewer_cannot_invite(client, auth_headers, second_user_headers):
	"""Viewer role cannot send invitations."""
	team = await create_team(client, auth_headers, "Viewer Limit Team")

	# Invite second user as viewer
	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "viewer@example.com",
		"role": "viewer",
	})
	token = inv.json()["token"]
	await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)

	# Viewer tries to invite another user
	resp = await client.post(f"/teams/{team['id']}/invitations", headers=second_user_headers, json={
		"email": "another@example.com",
		"role": "editor",
	})
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_member_isolation_across_teams(client, auth_headers, second_user_headers):
	"""User only sees teams they belong to."""
	# auth_headers user creates Team A
	await create_team(client, auth_headers, "Team A")

	# second_user creates Team B
	await create_team(client, second_user_headers, "Team B")

	# auth_headers user should only see Team A
	resp = await client.get("/teams", headers=auth_headers)
	names = {t["name"] for t in resp.json()["teams"]}
	assert "Team A" in names
	assert "Team B" not in names


# ---------------------------------------------------------------------------
# RBAC unit-level tests (service layer logic via API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rbac_editor_cannot_delete_project(client, auth_headers, second_user_headers):
	"""Editor role does not grant projects.delete permission (returns 403 via API)."""
	team = await create_team(client, auth_headers, "Editor Limits")

	# Invite second_user as editor
	inv = await client.post(f"/teams/{team['id']}/invitations", headers=auth_headers, json={
		"email": "editor@example.com",
		"role": "editor",
	})
	token = inv.json()["token"]
	await client.post(f"/teams/invitations/{token}/accept", headers=second_user_headers)

	# Editor cannot delete the team
	resp = await client.delete(f"/teams/{team['id']}", headers=second_user_headers)
	assert resp.status_code == 403
