"""Integration tests for usage metering and plan-limit enforcement (#297).

Proves the previously-dead `usage_service` functions are now wired at the request
boundary: episode/API counters increment, free-tier limits return 402, and
unlimited (enterprise) tiers are never blocked. Uses the real-DB `test_db`/`client`
fixtures with per-test transaction rollback.
"""

import pytest
from uuid import uuid4

from src.models.billing_subscription import BillingSubscription
from src.models.billing_usage import BillingUsage
from src.services.auth_service import verify_jwt_token
from src.services.usage_service import _current_period_dates
from src.utils.pricing import get_tier_limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def register(client, email=None):
	"""Register a free-tier user; return (headers, user_id, tenant_id)."""
	if email is None:
		email = f"usage_{uuid4()}@example.com"
	resp = await client.post("/auth/register", json={
		"email": email,
		"password": "SecurePass123!",
		"full_name": "Usage Test",
	})
	assert resp.status_code == 201, resp.text
	token = resp.json()["access_token"]
	payload = verify_jwt_token(token)
	return (
		{"Authorization": f"Bearer {token}"},
		payload["sub"],
		payload["tenant_id"],
	)


async def make_project(client, headers):
	resp = await client.post("/projects", headers=headers, json={
		"name": "Usage Project",
		"podcast_metadata": {"show_title": "S", "author": "A", "description": "D"},
	})
	assert resp.status_code == 201, resp.text
	return resp.json()["id"]


async def create_episode(client, headers, project_id, number):
	return await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": number,
		"episode_metadata": {"title": f"Ep {number}", "description": "d"},
	})


async def seed_subscription(test_db, user_id, tenant_id, tier):
	test_db.add(BillingSubscription(user_id=user_id, tenant_id=tenant_id, tier=tier))
	await test_db.flush()


async def seed_usage(test_db, user_id, tenant_id, **counters):
	"""Set current-period usage counters, upserting the period row.

	API metering may already have created the row for this request, so update it
	in place when present rather than inserting a conflicting duplicate.
	"""
	from sqlalchemy import select
	start, end = _current_period_dates()
	existing = (await test_db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == start,
		)
	)).scalar_one_or_none()
	if existing is None:
		test_db.add(BillingUsage(
			user_id=user_id, tenant_id=tenant_id,
			period_start=start, period_end=end, **counters,
		))
	else:
		for key, value in counters.items():
			setattr(existing, key, value)
	await test_db.flush()


# ---------------------------------------------------------------------------
# Episode quota enforcement & metering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_episode_creation_blocked_at_free_limit(client):
	headers, _, _ = await register(client)
	project_id = await make_project(client, headers)
	free_limit = get_tier_limit("free", "episodes_per_month")

	for i in range(1, free_limit + 1):
		resp = await create_episode(client, headers, project_id, i)
		assert resp.status_code == 201, resp.text

	# The (limit+1)-th creation is rejected with 402 Payment Required.
	resp = await create_episode(client, headers, project_id, free_limit + 1)
	assert resp.status_code == 402, resp.text
	assert "limit" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_episode_counter_increments_only_on_success(client):
	headers, _, _ = await register(client)
	project_id = await make_project(client, headers)
	free_limit = get_tier_limit("free", "episodes_per_month")

	for i in range(1, free_limit + 1):
		assert (await create_episode(client, headers, project_id, i)).status_code == 201

	usage = await client.get("/billing/usage", headers=headers)
	assert usage.json()["usage"]["episodes"]["count"] == free_limit

	# Over-limit attempt is rejected and must NOT bump the counter.
	assert (await create_episode(client, headers, project_id, free_limit + 1)).status_code == 402
	usage = await client.get("/billing/usage", headers=headers)
	assert usage.json()["usage"]["episodes"]["count"] == free_limit


@pytest.mark.asyncio
async def test_enterprise_episodes_not_blocked(client, test_db):
	headers, user_id, tenant_id = await register(client)
	await seed_subscription(test_db, user_id, tenant_id, tier="enterprise")
	project_id = await make_project(client, headers)
	free_limit = get_tier_limit("free", "episodes_per_month")

	# Enterprise is unlimited: creating beyond the free cap still succeeds.
	for i in range(1, free_limit + 3):
		resp = await create_episode(client, headers, project_id, i)
		assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# API-call metering & limit enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_calls_increase_monotonically(client):
	headers, _, _ = await register(client)
	first = (await client.get("/billing/usage", headers=headers)).json()["usage"]["api_calls"]["count"]
	second = (await client.get("/billing/usage", headers=headers)).json()["usage"]["api_calls"]["count"]
	# Reading usage is itself a metered call, so assert strict increase.
	assert second > first


@pytest.mark.asyncio
async def test_api_call_blocked_at_free_cap(client, test_db):
	headers, user_id, tenant_id = await register(client)
	cap = get_tier_limit("free", "api_calls_per_month")
	await seed_usage(test_db, user_id, tenant_id, api_calls=cap)

	# A normal (non-billing) endpoint is blocked once the cap is reached.
	resp = await client.get("/projects", headers=headers)
	assert resp.status_code == 402, resp.text


@pytest.mark.asyncio
async def test_billing_endpoints_reachable_at_api_cap(client, test_db):
	"""Over-quota users must still reach billing to view usage / upgrade."""
	headers, user_id, tenant_id = await register(client)
	cap = get_tier_limit("free", "api_calls_per_month")
	await seed_usage(test_db, user_id, tenant_id, api_calls=cap)

	resp = await client.get("/billing/usage", headers=headers)
	assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_enterprise_api_calls_not_blocked(client, test_db):
	headers, user_id, tenant_id = await register(client)
	await seed_subscription(test_db, user_id, tenant_id, tier="enterprise")
	cap = get_tier_limit("free", "api_calls_per_month")
	await seed_usage(test_db, user_id, tenant_id, api_calls=cap + 10)

	resp = await client.get("/billing/usage", headers=headers)
	assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_public_paths_not_metered(client):
	# Health is public: no auth, no metering, no error.
	assert (await client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_non_access_token_not_metered_returns_401(client, test_db):
	"""A non-access token must be rejected by auth (401), never pre-empted by a
	metering 402 — even when the user is already over the API cap."""
	from uuid import UUID
	from src.services.auth_service import create_verification_token

	_, user_id, tenant_id = await register(client)
	cap = get_tier_limit("free", "api_calls_per_month")
	await seed_usage(test_db, user_id, tenant_id, api_calls=cap)

	verification_token = create_verification_token(
		UUID(user_id), "x@example.com", UUID(tenant_id)
	)
	resp = await client.get(
		"/projects", headers={"Authorization": f"Bearer {verification_token}"}
	)
	assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Batch creation honours the same gate + tracking (adaptation beyond CR plan)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_creation_metered_and_gated(client, test_db):
	headers, user_id, tenant_id = await register(client)
	project_id = await make_project(client, headers)
	free_limit = get_tier_limit("free", "episodes_per_month")

	# Pre-fill the period to one below the free cap so only one slot remains.
	await seed_usage(test_db, user_id, tenant_id, episodes_created=free_limit - 1)

	# A batch of 3 would exceed the remaining quota → rejected before any write.
	resp = await client.post("/episodes/batch", headers=headers, json={
		"episodes": [
			{"project_id": project_id, "episode_number": n,
			 "episode_metadata": {"title": f"B{n}", "description": "d"}}
			for n in range(1, 4)
		]
	})
	assert resp.status_code == 402, resp.text


@pytest.mark.asyncio
async def test_batch_creation_increments_counter(client):
	headers, _, _ = await register(client)
	project_id = await make_project(client, headers)

	resp = await client.post("/episodes/batch", headers=headers, json={
		"episodes": [
			{"project_id": project_id, "episode_number": n,
			 "episode_metadata": {"title": f"B{n}", "description": "d"}}
			for n in range(1, 3)
		]
	})
	assert resp.status_code == 202, resp.text

	usage = await client.get("/billing/usage", headers=headers)
	assert usage.json()["usage"]["episodes"]["count"] == 2
