"""
Integration tests for the /billing endpoints.
"""

import pytest
from uuid import uuid4

from httpx import AsyncClient


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
async def test_get_subscription_requires_auth(client):
	response = await client.get("/billing/subscription")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_checkout_requires_auth(client):
	response = await client.post("/billing/checkout", json={"tier": "pro"})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_subscription_requires_auth(client):
	response = await client.patch("/billing/subscription", json={"action": "cancel"})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_usage_requires_auth(client):
	response = await client.get("/billing/usage")
	assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /billing/subscription — overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_subscription_new_user_defaults_to_free(client):
	"""New users should get a free-tier subscription auto-created."""
	headers = await register_and_login(client)
	response = await client.get("/billing/subscription", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["subscription"]["tier"] == "free"
	assert data["subscription"]["status"] == "active"
	assert "usage" in data
	assert "features" in data
	assert "overage" in data


@pytest.mark.asyncio
async def test_get_subscription_usage_starts_at_zero(client):
	"""New user's usage should be zero."""
	headers = await register_and_login(client)
	response = await client.get("/billing/subscription", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["usage"]["episodes_created"] == 0
	assert data["usage"]["api_calls"] == 0


@pytest.mark.asyncio
async def test_get_subscription_free_tier_features(client):
	"""Free tier should have episode limit of 5."""
	headers = await register_and_login(client)
	response = await client.get("/billing/subscription", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["usage"]["episodes_limit"] == 5
	assert data["usage"]["storage_limit_bytes"] == 1 * 1024 ** 3


# ---------------------------------------------------------------------------
# POST /billing/checkout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_creates_session_for_pro(client):
	"""Should return a checkout URL for pro tier."""
	headers = await register_and_login(client)
	response = await client.post("/billing/checkout", headers=headers, json={"tier": "pro"})
	assert response.status_code == 201
	data = response.json()
	assert "checkout_url" in data
	assert "pro" in data["checkout_url"] or "stripe.com" in data["checkout_url"]


@pytest.mark.asyncio
async def test_checkout_rejects_free_tier(client):
	"""Free tier is not valid for checkout (it's the default)."""
	headers = await register_and_login(client)
	response = await client.post("/billing/checkout", headers=headers, json={"tier": "free"})
	assert response.status_code == 422  # validation error from pydantic pattern


@pytest.mark.asyncio
async def test_checkout_rejects_unknown_tier(client):
	"""Unknown tiers should fail validation."""
	headers = await register_and_login(client)
	response = await client.post("/billing/checkout", headers=headers, json={"tier": "gold"})
	assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /billing/subscription — upgrade/downgrade/cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_subscription_to_pro(client):
	"""Should upgrade user to pro tier."""
	headers = await register_and_login(client)
	response = await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "upgrade", "tier": "pro"},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["tier"] == "pro"
	assert data["status"] == "active"


@pytest.mark.asyncio
async def test_downgrade_subscription_to_free(client):
	"""Should downgrade back to free tier."""
	headers = await register_and_login(client)
	# First upgrade
	await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "upgrade", "tier": "pro"},
	)
	# Then downgrade
	response = await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "downgrade", "tier": "free"},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["tier"] == "free"


@pytest.mark.asyncio
async def test_cancel_subscription_at_period_end(client):
	"""Cancel at period end should set auto_renew=False."""
	headers = await register_and_login(client)
	response = await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "cancel", "at_period_end": True},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["auto_renew"] is False


@pytest.mark.asyncio
async def test_cancel_subscription_immediately(client):
	"""Immediate cancel should set status to canceled."""
	headers = await register_and_login(client)
	response = await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "cancel", "at_period_end": False},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["status"] == "canceled"


@pytest.mark.asyncio
async def test_upgrade_without_tier_returns_error(client):
	"""Upgrade action requires tier field."""
	headers = await register_and_login(client)
	response = await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "upgrade"},
	)
	assert response.status_code == 400


@pytest.mark.asyncio
async def test_unknown_action_returns_error(client):
	"""Unknown action should return 400."""
	headers = await register_and_login(client)
	response = await client.patch(
		"/billing/subscription",
		headers=headers,
		json={"action": "freeze"},
	)
	assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /billing/usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_usage_returns_period_and_metrics(client):
	"""Usage endpoint should return period and metric breakdown."""
	headers = await register_and_login(client)
	response = await client.get("/billing/usage", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert "period" in data
	assert "start" in data["period"]
	assert "end" in data["period"]
	assert "usage" in data
	assert "episodes" in data["usage"]
	assert "storage" in data["usage"]
	assert "api_calls" in data["usage"]
	assert "overage_charges" in data


@pytest.mark.asyncio
async def test_get_usage_episodes_count_is_zero_initially(client):
	headers = await register_and_login(client)
	response = await client.get("/billing/usage", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["usage"]["episodes"]["count"] == 0
	assert data["usage"]["episodes"]["limit"] == 5  # free tier limit


@pytest.mark.asyncio
async def test_get_usage_free_tier_percentages(client):
	"""Free tier usage should show percent as 0.0 when no usage."""
	headers = await register_and_login(client)
	response = await client.get("/billing/usage", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["usage"]["episodes"]["percent"] == 0.0


# ---------------------------------------------------------------------------
# POST /billing/webhooks/stripe — public endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stripe_webhook_no_auth_required(client):
	"""Webhook endpoint should not require auth."""
	import json
	payload = json.dumps({
		"type": "customer.subscription.updated",
		"data": {"object": {"id": "sub_test", "customer": "cus_test", "status": "active"}},
	}).encode()
	response = await client.post(
		"/billing/webhooks/stripe",
		content=payload,
		headers={"Content-Type": "application/json"},
	)
	# Should not return 401; returns 200 with ignored/processed status
	assert response.status_code == 200


@pytest.mark.asyncio
async def test_stripe_webhook_returns_status(client):
	"""Webhook should return a status field in response."""
	import json
	payload = json.dumps({
		"type": "customer.subscription.deleted",
		"data": {"object": {"customer": "cus_nonexistent"}},
	}).encode()
	response = await client.post(
		"/billing/webhooks/stripe",
		content=payload,
		headers={"Content-Type": "application/json"},
	)
	assert response.status_code == 200
	data = response.json()
	assert "status" in data


# ---------------------------------------------------------------------------
# Unit tests for pricing config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pricing_config_free_tier():
	"""Free tier should have episode limit of 5."""
	from src.utils.pricing import get_tier_limit, is_unlimited
	assert get_tier_limit("free", "episodes_per_month") == 5
	assert is_unlimited("free", "episodes_per_month") is False


@pytest.mark.asyncio
async def test_pricing_config_enterprise_unlimited():
	"""Enterprise tier should have unlimited episodes."""
	from src.utils.pricing import get_tier_limit, is_unlimited
	assert get_tier_limit("enterprise", "episodes_per_month") is None
	assert is_unlimited("enterprise", "episodes_per_month") is True


@pytest.mark.asyncio
async def test_pricing_config_pro_tier():
	"""Pro tier should have 100 episodes per month."""
	from src.utils.pricing import get_tier_limit
	assert get_tier_limit("pro", "episodes_per_month") == 100
	assert get_tier_limit("pro", "storage_gb") == 50


@pytest.mark.asyncio
async def test_stripe_webhook_rejects_missing_signature_when_enabled(
	client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
	"""Issue #216: with billing enabled + secret configured, a request without a
	Stripe-Signature header is rejected with 400 — never parsed unsigned."""
	import types
	import src.services.billing_service as bs
	from src.config import settings

	# Enable billing with a fake stripe module (the real one isn't installed).
	fake = types.SimpleNamespace(
		api_key=None,
		Webhook=types.SimpleNamespace(construct_event=lambda *a, **k: {}),
		error=types.SimpleNamespace(SignatureVerificationError=type("E", (Exception,), {})),
	)
	monkeypatch.setattr(bs, "_STRIPE_AVAILABLE", True)
	monkeypatch.setattr(bs, "_stripe_module", fake)
	monkeypatch.setattr(bs, "_get_stripe_key", lambda: "sk_test_fake")
	monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test", raising=False)

	import json
	payload = json.dumps({"type": "customer.subscription.updated", "data": {"object": {}}}).encode()
	response = await client.post(
		"/billing/webhooks/stripe",
		content=payload,
		headers={"Content-Type": "application/json"},  # no stripe-signature header
	)
	assert response.status_code == 400
