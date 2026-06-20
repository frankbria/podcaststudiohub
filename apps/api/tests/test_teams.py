"""
Integration tests for the /teams endpoints.

Requires a running PostgreSQL instance with migrations applied.
"""

import pytest
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def register_and_login(client, email=None):
	"""Register a new user and return auth headers."""
	if email is None:
		email = f"test_{uuid4()}@example.com"
	response = await client.post("/auth/register", json={
		"email": email,
		"password": "SecurePass123!",
		"full_name": "Test User",
	})
	assert response.status_code == 201, response.text
	token = response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_team_requires_auth(client):
	response = await client.post("/teams", json={"name": "No Auth"})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_teams_requires_auth(client):
	response = await client.get("/teams")
	assert response.status_code == 401


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_team(client):
	headers = await register_and_login(client)
	response = await client.post("/teams", headers=headers, json={
		"name": "Podcast Studio A",
		"description": "Our main team",
	})
	assert response.status_code == 201
	data = response.json()
	assert data["name"] == "Podcast Studio A"
	assert data["description"] == "Our main team"
	assert data["tier"] == "free"
	assert data["member_count"] == 1
	assert "id" in data


@pytest.mark.asyncio
async def test_create_team_creator_is_owner(client):
	"""After creating a team the creator should appear as 'owner' in members."""
	headers = await register_and_login(client)
	create_resp = await client.post("/teams", headers=headers, json={"name": "Owner Test"})
	assert create_resp.status_code == 201
	team_id = create_resp.json()["id"]

	members_resp = await client.get(f"/teams/{team_id}/members", headers=headers)
	assert members_resp.status_code == 200
	members = members_resp.json()
	assert len(members) == 1
	assert members[0]["role"] == "owner"


@pytest.mark.asyncio
async def test_list_teams_initially_empty(client):
	headers = await register_and_login(client)
	response = await client.get("/teams", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["teams"] == []
	assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_teams_shows_created_teams(client):
	headers = await register_and_login(client)
	await client.post("/teams", headers=headers, json={"name": "Team Alpha"})
	await client.post("/teams", headers=headers, json={"name": "Team Beta"})
	response = await client.get("/teams", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_team(client):
	headers = await register_and_login(client)
	create_resp = await client.post("/teams", headers=headers, json={"name": "Get Me"})
	team_id = create_resp.json()["id"]

	response = await client.get(f"/teams/{team_id}", headers=headers)
	assert response.status_code == 200
	assert response.json()["id"] == team_id


@pytest.mark.asyncio
async def test_get_team_not_found(client):
	headers = await register_and_login(client)
	response = await client.get(f"/teams/{uuid4()}", headers=headers)
	assert response.status_code == 403  # not a member → permission denied


@pytest.mark.asyncio
async def test_update_team(client):
	headers = await register_and_login(client)
	create_resp = await client.post("/teams", headers=headers, json={"name": "Old Name"})
	team_id = create_resp.json()["id"]

	update_resp = await client.patch(f"/teams/{team_id}", headers=headers, json={
		"name": "New Name",
		"description": "Updated",
	})
	assert update_resp.status_code == 200
	assert update_resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_team(client):
	headers = await register_and_login(client)
	create_resp = await client.post("/teams", headers=headers, json={"name": "Temp Team"})
	team_id = create_resp.json()["id"]

	del_resp = await client.delete(f"/teams/{team_id}", headers=headers)
	assert del_resp.status_code == 204

	# Team should no longer appear in list
	list_resp = await client.get("/teams", headers=headers)
	assert list_resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Permission enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_member_cannot_access_team(client):
	owner_headers = await register_and_login(client)
	stranger_headers = await register_and_login(client)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Private"})
	team_id = create_resp.json()["id"]

	# Stranger has no membership → 403
	response = await client.get(f"/teams/{team_id}", headers=stranger_headers)
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_owner_cannot_update_team(client):
	"""Editors do not have team.edit permission and should receive 403."""
	owner_headers = await register_and_login(client)
	editor_email = f"editor_{uuid4()}@example.com"
	editor_headers = await register_and_login(client, editor_email)

	# Create team and invite editor
	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Perm Test"})
	team_id = create_resp.json()["id"]

	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": editor_email, "role": "editor"},
	)
	assert inv_resp.status_code == 201
	token = inv_resp.json()["token"]

	# Editor accepts
	accept_resp = await client.post(f"/teams/invitations/{token}/accept", headers=editor_headers)
	assert accept_resp.status_code == 201

	# Editor tries to update team → 403
	update_resp = await client.patch(
		f"/teams/{team_id}",
		headers=editor_headers,
		json={"name": "Hijacked"},
	)
	assert update_resp.status_code == 403


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invitation_flow(client):
	"""Full invitation: create → list → accept → member appears."""
	owner_headers = await register_and_login(client)
	invitee_email = f"invitee_{uuid4()}@example.com"
	invitee_headers = await register_and_login(client, invitee_email)

	# Create team
	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Invite Test"})
	team_id = create_resp.json()["id"]

	# Send invitation
	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": invitee_email, "role": "viewer"},
	)
	assert inv_resp.status_code == 201
	token = inv_resp.json()["token"]
	assert inv_resp.json()["status"] == "pending"

	# List invitations
	list_resp = await client.get(f"/teams/{team_id}/invitations", headers=owner_headers)
	assert list_resp.status_code == 200
	assert len(list_resp.json()) == 1

	# Accept
	accept_resp = await client.post(f"/teams/invitations/{token}/accept", headers=invitee_headers)
	assert accept_resp.status_code == 201
	assert accept_resp.json()["role"] == "viewer"

	# Invitee now appears in members
	members_resp = await client.get(f"/teams/{team_id}/members", headers=owner_headers)
	assert members_resp.status_code == 200
	member_user_ids = [m["user_id"] for m in members_resp.json()]
	assert accept_resp.json()["user_id"] in member_user_ids


@pytest.mark.asyncio
async def test_accept_invitation_twice_fails(client):
	"""Accepting an already-accepted invitation should fail."""
	owner_headers = await register_and_login(client)
	invitee_email = f"inv2_{uuid4()}@example.com"
	invitee_headers = await register_and_login(client, invitee_email)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Dupe Test"})
	team_id = create_resp.json()["id"]

	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": invitee_email, "role": "editor"},
	)
	token = inv_resp.json()["token"]

	# First accept succeeds
	r1 = await client.post(f"/teams/invitations/{token}/accept", headers=invitee_headers)
	assert r1.status_code == 201

	# Second accept fails
	r2 = await client.post(f"/teams/invitations/{token}/accept", headers=invitee_headers)
	assert r2.status_code == 400


@pytest.mark.asyncio
async def test_invalid_invitation_token_returns_404(client):
	headers = await register_and_login(client)
	response = await client.post("/teams/invitations/notarealtoken/accept", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_invitation_wrong_email_rejected(client: AsyncClient) -> None:
	"""A user whose email differs from the invited email cannot accept (403)."""
	owner_headers = await register_and_login(client)
	invited_email = f"invited_{uuid4()}@example.com"
	# A different user (different email) tries to accept the token.
	stranger_headers = await register_and_login(client)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Bound Invite"})
	team_id = create_resp.json()["id"]

	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": invited_email, "role": "viewer"},
	)
	token = inv_resp.json()["token"]

	resp = await client.post(f"/teams/invitations/{token}/accept", headers=stranger_headers)
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_accept_invitation_case_variant_account_rejected(client: AsyncClient) -> None:
	"""A case-variant account cannot accept a token addressed to another email.

	Account emails are case-sensitive (auth_service), so victim@ and VICTIM@ are
	distinct accounts. The email binding must reject the variant (403), otherwise
	an attacker could register a case-variant and accept a leaked token.
	"""
	owner_headers = await register_and_login(client)
	local = f"casevariant_{uuid4().hex}"
	invited_email = f"{local}@example.com"
	# Attacker registers the upper-cased variant — a different account.
	attacker_headers = await register_and_login(client, invited_email.upper())

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Case Invite"})
	team_id = create_resp.json()["id"]

	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": invited_email, "role": "viewer"},
	)
	token = inv_resp.json()["token"]

	resp = await client.post(f"/teams/invitations/{token}/accept", headers=attacker_headers)
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_invite_as_owner(client: AsyncClient) -> None:
	"""Ownership is not grantable via invitation (schema rejects role=owner)."""
	owner_headers = await register_and_login(client)
	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "No Owner Invite"})
	team_id = create_resp.json()["id"]

	resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": f"co_{uuid4()}@example.com", "role": "owner"},
	)
	assert resp.status_code == 422


@pytest.mark.asyncio
async def test_legacy_owner_invitation_rejected_on_accept(
	client: AsyncClient,
	test_db: AsyncSession,
) -> None:
	"""A pre-existing owner invitation (issued before role restriction) cannot
	be accepted — the role guard is enforced at acceptance, not just creation."""
	from datetime import datetime, timedelta
	import secrets
	from uuid import UUID
	from src.models.team_invitation import TeamInvitation

	owner_headers = await register_and_login(client)
	invitee_email = f"legacy_{uuid4()}@example.com"
	invitee_headers = await register_and_login(client, invitee_email)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Legacy Owner"})
	team_id = create_resp.json()["id"]
	members = await client.get(f"/teams/{team_id}/members", headers=owner_headers)
	inviter_id = members.json()[0]["user_id"]

	# Insert directly to bypass schema validation, simulating a token created
	# before `owner` was removed from invitable roles.
	token = secrets.token_urlsafe(32)
	test_db.add(TeamInvitation(
		team_id=UUID(team_id),
		inviter_id=UUID(inviter_id),
		email=invitee_email,
		role="owner",
		token=token,
		status="pending",
		expires_at=datetime.utcnow() + timedelta(days=7),
	))
	await test_db.flush()

	resp = await client.post(f"/teams/invitations/{token}/accept", headers=invitee_headers)
	assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Non-member access is rejected on every team route (regression for #218)
# ---------------------------------------------------------------------------


# One case per route. Parametrized (not looped in a single test) because the
# test-db fixture rolls its savepoint back on the first permission-denied
# response, which would erase the registered users for any later request.
NON_MEMBER_ROUTES: list[tuple[str, str, dict[str, str] | None]] = [
	("get", "/teams/{team_id}", None),
	("patch", "/teams/{team_id}", {"name": "Hijack"}),
	("delete", "/teams/{team_id}", None),
	("get", "/teams/{team_id}/members", None),
	("patch", "/teams/{team_id}/members/{other_user}", {"role": "editor"}),
	("delete", "/teams/{team_id}/members/{other_user}", None),
	("post", "/teams/{team_id}/invitations", {"email": "outsider@example.com", "role": "viewer"}),
	("get", "/teams/{team_id}/invitations", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,url_tmpl,body", NON_MEMBER_ROUTES)
async def test_non_member_blocked_on_team_route(
	client: AsyncClient,
	method: str,
	url_tmpl: str,
	body: dict[str, str] | None,
) -> None:
	"""A non-member receives 403 on every membership-scoped team route (#218)."""
	owner_headers = await register_and_login(client)
	stranger_headers = await register_and_login(client)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Locked Down"})
	team_id = create_resp.json()["id"]

	url = url_tmpl.format(team_id=team_id, other_user=uuid4())
	kwargs = {"headers": stranger_headers}
	if body is not None:
		kwargs["json"] = body
	resp = await getattr(client, method)(url, **kwargs)
	assert resp.status_code == 403, f"{method.upper()} {url} -> {resp.status_code}"


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_member_role(client):
	owner_headers = await register_and_login(client)
	member_email = f"member_{uuid4()}@example.com"
	member_headers = await register_and_login(client, member_email)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Role Update"})
	team_id = create_resp.json()["id"]

	# Invite as viewer
	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": member_email, "role": "viewer"},
	)
	token = inv_resp.json()["token"]
	accept_resp = await client.post(f"/teams/invitations/{token}/accept", headers=member_headers)
	user_id = accept_resp.json()["user_id"]

	# Promote to editor
	patch_resp = await client.patch(
		f"/teams/{team_id}/members/{user_id}",
		headers=owner_headers,
		json={"role": "editor"},
	)
	assert patch_resp.status_code == 200
	assert patch_resp.json()["role"] == "editor"


@pytest.mark.asyncio
async def test_remove_member(client):
	owner_headers = await register_and_login(client)
	member_email = f"rm_{uuid4()}@example.com"
	member_headers = await register_and_login(client, member_email)

	create_resp = await client.post("/teams", headers=owner_headers, json={"name": "Remove Test"})
	team_id = create_resp.json()["id"]

	inv_resp = await client.post(
		f"/teams/{team_id}/invitations",
		headers=owner_headers,
		json={"email": member_email, "role": "viewer"},
	)
	token = inv_resp.json()["token"]
	accept_resp = await client.post(f"/teams/invitations/{token}/accept", headers=member_headers)
	user_id = accept_resp.json()["user_id"]

	# Remove member
	del_resp = await client.delete(f"/teams/{team_id}/members/{user_id}", headers=owner_headers)
	assert del_resp.status_code == 204

	# Member count back to 1 (just owner)
	team_resp = await client.get(f"/teams/{team_id}", headers=owner_headers)
	assert team_resp.json()["member_count"] == 1
