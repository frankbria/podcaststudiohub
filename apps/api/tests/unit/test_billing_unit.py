"""
Unit tests for billing service, usage service, and pricing config.
These tests do not require a database connection.
"""

import types
from typing import Any, Callable
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tests.unit.conftest import _register_user


# ---------------------------------------------------------------------------
# Pricing config tests
# ---------------------------------------------------------------------------


class TestPricingConfig:
	def test_free_tier_episodes_limit(self):
		from src.utils.pricing import get_tier_limit
		assert get_tier_limit("free", "episodes_per_month") == 5

	def test_pro_tier_episodes_limit(self):
		from src.utils.pricing import get_tier_limit
		assert get_tier_limit("pro", "episodes_per_month") == 100

	def test_enterprise_tier_episodes_unlimited(self):
		from src.utils.pricing import get_tier_limit, is_unlimited
		assert get_tier_limit("enterprise", "episodes_per_month") is None
		assert is_unlimited("enterprise", "episodes_per_month") is True

	def test_free_tier_storage_limit(self):
		from src.utils.pricing import get_tier_limit
		assert get_tier_limit("free", "storage_gb") == 1

	def test_pro_tier_storage_limit(self):
		from src.utils.pricing import get_tier_limit
		assert get_tier_limit("pro", "storage_gb") == 50

	def test_unknown_tier_defaults_to_free(self):
		from src.utils.pricing import get_tier_features
		features = get_tier_features("unknown_tier")
		free_features = get_tier_features("free")
		assert features == free_features

	def test_get_tier_features_returns_dict(self):
		from src.utils.pricing import get_tier_features
		features = get_tier_features("pro")
		assert isinstance(features, dict)
		assert "episodes_per_month" in features
		assert "storage_gb" in features

	def test_is_unlimited_free_tier(self):
		from src.utils.pricing import is_unlimited
		assert is_unlimited("free", "episodes_per_month") is False
		assert is_unlimited("free", "storage_gb") is False

	def test_overage_pricing_defined(self):
		from src.utils.pricing import OVERAGE_PRICING
		assert "cost_per_episode_over_limit" in OVERAGE_PRICING
		assert "cost_per_gb_per_month" in OVERAGE_PRICING
		assert OVERAGE_PRICING["cost_per_episode_over_limit"] == 2.00
		assert OVERAGE_PRICING["cost_per_gb_per_month"] == 0.50


# ---------------------------------------------------------------------------
# Current period dates
# ---------------------------------------------------------------------------


class TestCurrentPeriodDates:
	def test_period_start_is_first_of_month(self):
		from src.services.usage_service import _current_period_dates
		start, end = _current_period_dates()
		assert start.day == 1

	def test_period_end_is_first_of_next_month(self):
		from src.services.usage_service import _current_period_dates
		start, end = _current_period_dates()
		assert end.day == 1
		assert end > start

	def test_period_start_end_adjacent_months(self):
		from src.services.usage_service import _current_period_dates
		start, end = _current_period_dates()
		# end should be exactly one month after start
		if start.month == 12:
			assert end.month == 1
			assert end.year == start.year + 1
		else:
			assert end.month == start.month + 1
			assert end.year == start.year


# ---------------------------------------------------------------------------
# Stripe enabled check
# ---------------------------------------------------------------------------


class TestStripeEnabled:
	def test_stripe_disabled_without_key(self, monkeypatch):
		"""When no STRIPE_SECRET_KEY is set, _stripe_enabled should be False."""
		import src.services.billing_service as bs
		monkeypatch.setattr(bs, "_get_stripe_key", lambda: None)
		assert bs._stripe_enabled() is False

	def test_stripe_disabled_when_stripe_not_installed(self, monkeypatch):
		"""When stripe module is unavailable, _stripe_enabled should be False."""
		import src.services.billing_service as bs
		monkeypatch.setattr(bs, "_STRIPE_AVAILABLE", False)
		monkeypatch.setattr(bs, "_get_stripe_key", lambda: "fake-stripe-key")
		assert bs._stripe_enabled() is False


# ---------------------------------------------------------------------------
# Stripe status mapping
# ---------------------------------------------------------------------------


class TestStripeStatusMapping:
	def test_active_status(self):
		from src.services.billing_service import _map_stripe_status
		from src.models.billing_subscription import SubscriptionStatus
		assert _map_stripe_status("active") == SubscriptionStatus.ACTIVE

	def test_past_due_status(self):
		from src.services.billing_service import _map_stripe_status
		from src.models.billing_subscription import SubscriptionStatus
		assert _map_stripe_status("past_due") == SubscriptionStatus.PAST_DUE

	def test_canceled_status(self):
		from src.services.billing_service import _map_stripe_status
		from src.models.billing_subscription import SubscriptionStatus
		assert _map_stripe_status("canceled") == SubscriptionStatus.CANCELED

	def test_unknown_status_defaults_to_active(self):
		from src.services.billing_service import _map_stripe_status
		from src.models.billing_subscription import SubscriptionStatus
		assert _map_stripe_status("some_unknown_status") == SubscriptionStatus.ACTIVE


# ---------------------------------------------------------------------------
# Billing schemas validation
# ---------------------------------------------------------------------------


class TestBillingSchemas:
	def test_checkout_request_valid_pro(self):
		from src.schemas.billing import CheckoutRequest
		req = CheckoutRequest(tier="pro")
		assert req.tier == "pro"

	def test_checkout_request_valid_enterprise(self):
		from src.schemas.billing import CheckoutRequest
		req = CheckoutRequest(tier="enterprise")
		assert req.tier == "enterprise"

	def test_checkout_request_invalid_tier(self):
		from pydantic import ValidationError
		from src.schemas.billing import CheckoutRequest
		with pytest.raises(ValidationError):
			CheckoutRequest(tier="free")

	def test_checkout_request_unknown_tier(self):
		from pydantic import ValidationError
		from src.schemas.billing import CheckoutRequest
		with pytest.raises(ValidationError):
			CheckoutRequest(tier="gold")

	def test_subscription_update_cancel_action(self):
		from src.schemas.billing import SubscriptionUpdateRequest
		req = SubscriptionUpdateRequest(action="cancel")
		assert req.action == "cancel"
		assert req.at_period_end is True  # default

	def test_subscription_update_upgrade_action(self):
		from src.schemas.billing import SubscriptionUpdateRequest
		req = SubscriptionUpdateRequest(action="upgrade", tier="pro")
		assert req.action == "upgrade"
		assert req.tier == "pro"

	def test_subscription_update_invalid_action(self):
		from pydantic import ValidationError
		from src.schemas.billing import SubscriptionUpdateRequest
		with pytest.raises(ValidationError):
			SubscriptionUpdateRequest(action="invalid_action")


# ---------------------------------------------------------------------------
# Webhook signature enforcement (issue #216)
# ---------------------------------------------------------------------------


def _enable_stripe(
	monkeypatch: pytest.MonkeyPatch, construct_event: Callable[..., object]
) -> "tuple[Any, type[Exception]]":
	"""Enable Stripe in billing_service with a fake stripe module.

	Returns (module, SignatureVerificationError) so callers can raise the same
	error class the verifier catches.
	"""
	import src.services.billing_service as bs

	class _SigError(Exception):
		pass

	fake = types.SimpleNamespace()
	fake.Webhook = types.SimpleNamespace(construct_event=construct_event)
	fake.error = types.SimpleNamespace(SignatureVerificationError=_SigError)
	monkeypatch.setattr(bs, "_STRIPE_AVAILABLE", True)
	monkeypatch.setattr(bs, "_stripe_module", fake)
	monkeypatch.setattr(bs, "_get_stripe_key", lambda: "fake-stripe-key")
	return bs, _SigError


class TestProcessWebhookSignature:
	"""When Stripe is enabled, unsigned/unverified payloads must be rejected."""

	@pytest.mark.asyncio
	async def test_missing_signature_header_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""Enabled + secret configured + no Stripe-Signature header -> 400."""
		bs, _ = _enable_stripe(monkeypatch, MagicMock())
		with pytest.raises(HTTPException) as exc:
			await bs.process_webhook(MagicMock(), b"{}", None, "whsec_test")
		assert exc.value.status_code == 400

	@pytest.mark.asyncio
	async def test_missing_secret_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""Enabled but no webhook secret configured -> 400; never parse unsigned."""
		bs, _ = _enable_stripe(monkeypatch, MagicMock())
		with pytest.raises(HTTPException) as exc:
			await bs.process_webhook(MagicMock(), b"{}", "sig", None)
		assert exc.value.status_code == 400

	@pytest.mark.asyncio
	async def test_invalid_signature_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""Configured secret + invalid signature -> 400."""
		bs, SigError = _enable_stripe(monkeypatch, MagicMock())
		bs._stripe_module.Webhook.construct_event = MagicMock(
			side_effect=SigError("bad signature")
		)
		with pytest.raises(HTTPException) as exc:
			await bs.process_webhook(MagicMock(), b"{}", "sig", "whsec_test")
		assert exc.value.status_code == 400

	@pytest.mark.asyncio
	async def test_valid_signature_processed(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""Configured secret + valid signature -> event processed (verified path)."""
		event = {"type": "invoice.paid", "data": {"object": {}}}
		construct_event = MagicMock(return_value=event)
		bs, _ = _enable_stripe(monkeypatch, construct_event)
		result = await bs.process_webhook(MagicMock(), b"{}", "sig", "whsec_test")
		assert result["status"] == "processed"
		assert result["event_type"] == "invoice.paid"
		# The verified path was taken: signature was actually checked.
		construct_event.assert_called_once_with(b"{}", "sig", "whsec_test")

	@pytest.mark.asyncio
	async def test_disabled_stripe_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
		"""Stripe disabled -> ignored, no parsing (existing behavior preserved)."""
		import src.services.billing_service as bs
		monkeypatch.setattr(bs, "_get_stripe_key", lambda: None)
		result = await bs.process_webhook(MagicMock(), b"{}", None, None)
		assert result["status"] == "ignored"


class TestStripeSettings:
	"""Issue #216 AC1: secret + webhook secret must be real Settings fields."""

	def test_settings_expose_stripe_fields(self) -> None:
		from src.config import settings
		assert hasattr(settings, "STRIPE_SECRET_KEY")
		assert hasattr(settings, "STRIPE_WEBHOOK_SECRET")


# ---------------------------------------------------------------------------
# _get_stripe_key (real body, not monkeypatched)
# ---------------------------------------------------------------------------


class TestGetStripeKeyReal:
	def test_returns_none_when_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
		from src.config import settings
		from src.services.billing_service import _get_stripe_key
		monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None, raising=False)
		assert _get_stripe_key() is None

	def test_returns_configured_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
		from src.config import settings
		from src.services.billing_service import _get_stripe_key
		monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "fake-stripe-key", raising=False)
		assert _get_stripe_key() == "fake-stripe-key"


# ---------------------------------------------------------------------------
# get_subscription (plain lookup, not the get-or-create variant)
# ---------------------------------------------------------------------------


class TestGetSubscriptionPlain:
	@pytest.mark.asyncio
	async def test_returns_none_when_absent(self, test_db) -> None:
		from uuid import uuid4
		from src.services.billing_service import get_subscription
		assert await get_subscription(test_db, uuid4()) is None

	@pytest.mark.asyncio
	async def test_returns_existing_subscription(self, test_db, client) -> None:
		from src.services.billing_service import get_or_create_subscription, get_subscription
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		tenant_id = uuid4()
		created = await get_or_create_subscription(test_db, user_id, tenant_id)
		fetched = await get_subscription(test_db, user_id)
		assert fetched is not None
		assert fetched.id == created.id


# ---------------------------------------------------------------------------
# create_checkout_session — invalid tier and real-Stripe branches
# ---------------------------------------------------------------------------


class TestCreateCheckoutInvalidTier:
	@pytest.mark.asyncio
	async def test_invalid_tier_raises_400(self, test_db) -> None:
		from uuid import uuid4
		from src.services.billing_service import create_checkout_session
		with pytest.raises(HTTPException) as exc:
			await create_checkout_session(test_db, uuid4(), uuid4(), "invalid_tier")
		assert exc.value.status_code == 400


def _enable_fake_stripe_sdk(monkeypatch: pytest.MonkeyPatch):
	"""Enable billing_service's real-Stripe code path with a fake stripe SDK.

	The real `stripe` package isn't installed in this environment, so the
	Customer/Session creation calls are faked to exercise create_checkout_session's
	Stripe-enabled branch (lines otherwise unreachable in mock mode).
	"""
	import src.services.billing_service as bs

	fake_customer = types.SimpleNamespace(id="cus_fake123")
	fake_session = types.SimpleNamespace(url="https://checkout.stripe.com/session/test")
	fake = types.SimpleNamespace(
		api_key=None,
		Customer=types.SimpleNamespace(create=lambda **kwargs: fake_customer),
		checkout=types.SimpleNamespace(
			Session=types.SimpleNamespace(create=lambda **kwargs: fake_session)
		),
	)
	monkeypatch.setattr(bs, "_STRIPE_AVAILABLE", True)
	monkeypatch.setattr(bs, "_stripe_module", fake)
	monkeypatch.setattr(bs, "_get_stripe_key", lambda: "fake-stripe-key")
	return bs


class TestCreateCheckoutStripeEnabled:
	@pytest.mark.asyncio
	async def test_creates_stripe_session_for_new_customer(
		self, test_db, client, monkeypatch: pytest.MonkeyPatch
	) -> None:
		bs = _enable_fake_stripe_sdk(monkeypatch)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		tenant_id = uuid4()

		result = await bs.create_checkout_session(test_db, user_id, tenant_id, "pro")

		assert result["checkout_url"] == "https://checkout.stripe.com/session/test"
		sub = await bs.get_subscription(test_db, user_id)
		assert sub.stripe_customer_id == "cus_fake123"

	@pytest.mark.asyncio
	async def test_reuses_existing_stripe_customer(
		self, test_db, client, monkeypatch: pytest.MonkeyPatch
	) -> None:
		bs = _enable_fake_stripe_sdk(monkeypatch)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		tenant_id = uuid4()
		sub = await bs.get_or_create_subscription(test_db, user_id, tenant_id)
		sub.stripe_customer_id = "cus_existing"
		await test_db.commit()

		result = await bs.create_checkout_session(test_db, user_id, tenant_id, "pro")

		assert result["checkout_url"] == "https://checkout.stripe.com/session/test"
		await test_db.refresh(sub)
		assert sub.stripe_customer_id == "cus_existing"

	@pytest.mark.asyncio
	async def test_enterprise_requires_custom_pricing(
		self, test_db, client, monkeypatch: pytest.MonkeyPatch
	) -> None:
		bs = _enable_fake_stripe_sdk(monkeypatch)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		with pytest.raises(HTTPException) as exc:
			await bs.create_checkout_session(test_db, user_id, uuid4(), "enterprise")
		assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# update_subscription_tier — unknown tier branch
# ---------------------------------------------------------------------------


class TestUpdateSubscriptionTierUnknown:
	@pytest.mark.asyncio
	async def test_unknown_tier_raises_400(self, test_db) -> None:
		from uuid import uuid4
		from src.services.billing_service import update_subscription_tier
		with pytest.raises(HTTPException) as exc:
			await update_subscription_tier(test_db, uuid4(), uuid4(), "bogus_tier")
		assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# _handle_subscription_updated / _handle_subscription_deleted (direct calls)
# ---------------------------------------------------------------------------


class TestHandleSubscriptionUpdatedDirect:
	@pytest.mark.asyncio
	async def test_updates_matching_subscription(self, test_db, client) -> None:
		from src.models.billing_subscription import SubscriptionStatus
		from src.services.billing_service import (
			_handle_subscription_updated,
			get_or_create_subscription,
		)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		tenant_id = uuid4()
		sub = await get_or_create_subscription(test_db, user_id, tenant_id)
		sub.stripe_customer_id = "cus_matched"
		await test_db.commit()

		await _handle_subscription_updated(
			test_db, {"id": "sub_123", "customer": "cus_matched", "status": "past_due"}
		)

		await test_db.refresh(sub)
		assert sub.stripe_subscription_id == "sub_123"
		assert sub.status == SubscriptionStatus.PAST_DUE

	@pytest.mark.asyncio
	async def test_no_matching_subscription_is_a_noop(self, test_db, client) -> None:
		from src.models.billing_subscription import SubscriptionStatus
		from src.services.billing_service import (
			_handle_subscription_updated,
			get_or_create_subscription,
		)
		# Seed an existing subscription in a state distinct from what a match
		# would produce, so a false match would be visible below.
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		sub = await get_or_create_subscription(test_db, user_id, uuid4())
		sub.stripe_customer_id = "cus_unrelated"
		sub.status = SubscriptionStatus.PAST_DUE
		sub.stripe_subscription_id = "sub_preexisting"
		await test_db.commit()

		# Should return quietly; no subscription has this customer id.
		await _handle_subscription_updated(
			test_db, {"id": "sub_x", "customer": "cus_does_not_exist", "status": "active"}
		)

		await test_db.refresh(sub)
		assert sub.status == SubscriptionStatus.PAST_DUE
		assert sub.stripe_subscription_id == "sub_preexisting"


class TestHandleSubscriptionDeletedDirect:
	@pytest.mark.asyncio
	async def test_cancels_and_downgrades_matching_subscription(self, test_db, client) -> None:
		from src.models.billing_subscription import SubscriptionStatus, SubscriptionTier
		from src.services.billing_service import (
			_handle_subscription_deleted,
			get_or_create_subscription,
			update_subscription_tier,
		)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		tenant_id = uuid4()
		sub = await get_or_create_subscription(test_db, user_id, tenant_id)
		await update_subscription_tier(test_db, user_id, tenant_id, "pro")
		sub.stripe_customer_id = "cus_deleted"
		await test_db.commit()

		await _handle_subscription_deleted(test_db, {"customer": "cus_deleted"})

		await test_db.refresh(sub)
		assert sub.status == SubscriptionStatus.CANCELED
		assert sub.tier == SubscriptionTier.FREE
		assert sub.canceled_at is not None

	@pytest.mark.asyncio
	async def test_no_matching_subscription_is_a_noop(self, test_db, client) -> None:
		from src.models.billing_subscription import SubscriptionStatus, SubscriptionTier
		from src.services.billing_service import (
			_handle_subscription_deleted,
			get_or_create_subscription,
			update_subscription_tier,
		)
		# Seed an existing paid subscription; a false match here would cancel
		# and downgrade it, which the assertions below would catch.
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		tenant_id = uuid4()
		sub = await get_or_create_subscription(test_db, user_id, tenant_id)
		await update_subscription_tier(test_db, user_id, tenant_id, "pro")
		sub.stripe_customer_id = "cus_unrelated_2"
		await test_db.commit()

		await _handle_subscription_deleted(test_db, {"customer": "cus_does_not_exist_either"})

		await test_db.refresh(sub)
		assert sub.tier == SubscriptionTier.PRO
		assert sub.status == SubscriptionStatus.ACTIVE
		assert sub.canceled_at is None


# ---------------------------------------------------------------------------
# process_webhook — full dispatch to the subscription handlers (real db)
# ---------------------------------------------------------------------------


class TestProcessWebhookDispatchesToHandlers:
	@pytest.mark.asyncio
	async def test_subscription_updated_event_updates_db(
		self, test_db, client, monkeypatch: pytest.MonkeyPatch
	) -> None:
		construct_event = MagicMock(return_value={
			"type": "customer.subscription.updated",
			"data": {"object": {"id": "sub_new", "customer": "cus_dispatch", "status": "active"}},
		})
		bs, _ = _enable_stripe(monkeypatch, construct_event)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		sub = await bs.get_or_create_subscription(test_db, user_id, uuid4())
		sub.stripe_customer_id = "cus_dispatch"
		await test_db.commit()

		result = await bs.process_webhook(test_db, b"{}", "sig", "whsec_test")

		assert result["event_type"] == "customer.subscription.updated"
		await test_db.refresh(sub)
		assert sub.stripe_subscription_id == "sub_new"

	@pytest.mark.asyncio
	async def test_subscription_deleted_event_updates_db(
		self, test_db, client, monkeypatch: pytest.MonkeyPatch
	) -> None:
		from src.models.billing_subscription import SubscriptionStatus
		construct_event = MagicMock(return_value={
			"type": "customer.subscription.deleted",
			"data": {"object": {"customer": "cus_dispatch2"}},
		})
		bs, _ = _enable_stripe(monkeypatch, construct_event)
		user_id = await _register_user(client, email_prefix="billing_unit_", full_name="Billing Unit Test User")
		sub = await bs.get_or_create_subscription(test_db, user_id, uuid4())
		sub.stripe_customer_id = "cus_dispatch2"
		await test_db.commit()

		result = await bs.process_webhook(test_db, b"{}", "sig", "whsec_test")

		assert result["event_type"] == "customer.subscription.deleted"
		await test_db.refresh(sub)
		assert sub.status == SubscriptionStatus.CANCELED
