"""
Unit tests for billing service, usage service, and pricing config.
These tests do not require a database connection.
"""

import types
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


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
		monkeypatch.setattr(bs, "_get_stripe_key", lambda: "sk_test_fake")
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
	monkeypatch.setattr(bs, "_get_stripe_key", lambda: "sk_test_fake")
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
