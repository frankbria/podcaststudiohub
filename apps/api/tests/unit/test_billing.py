"""
Unit tests for billing pricing config, usage service, and billing service.

Uses AsyncMock database sessions — no real database required.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.billing_pricing import (
	PRICING_TIERS,
	get_tier_features,
	get_tier_price,
	is_unlimited,
)
from src.models.billing_subscription import BillingSubscription, SubscriptionTier
from src.models.billing_usage import BillingUsage
from src.services.usage_service import (
	_current_period_dates,
	calculate_overage_cost,
	check_api_limit,
	check_episode_limit,
)
from src.services.billing_service import (
	cancel_subscription,
	get_or_create_subscription,
	update_subscription_tier,
)


# ---------------------------------------------------------------------------
# billing_pricing tests
# ---------------------------------------------------------------------------

class TestPricingConfig:
	def test_all_tiers_present(self):
		assert "free" in PRICING_TIERS
		assert "pro" in PRICING_TIERS
		assert "enterprise" in PRICING_TIERS

	def test_free_tier_episodes_limit(self):
		features = get_tier_features("free")
		assert features["episodes_per_month"] == 5

	def test_pro_tier_episodes_limit(self):
		features = get_tier_features("pro")
		assert features["episodes_per_month"] == 100

	def test_enterprise_tier_unlimited_episodes(self):
		features = get_tier_features("enterprise")
		assert features["episodes_per_month"] == "unlimited"

	def test_free_price_is_zero(self):
		assert get_tier_price("free") == 0

	def test_pro_price_is_29(self):
		assert get_tier_price("pro") == 29

	def test_enterprise_price_is_none(self):
		assert get_tier_price("enterprise") is None

	def test_is_unlimited_true(self):
		assert is_unlimited("unlimited") is True

	def test_is_unlimited_false(self):
		assert is_unlimited(5) is False
		assert is_unlimited(0) is False

	def test_unknown_tier_falls_back_to_free(self):
		features = get_tier_features("unknown_tier")
		assert features["episodes_per_month"] == 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_usage(
	user_id=None,
	episodes_created=0,
	api_calls=0,
	storage_bytes=0,
	overage_cost=0,
):
	"""Helper to create a BillingUsage instance without a DB."""
	today = date.today()
	period_start = today.replace(day=1)
	usage = BillingUsage()
	usage.id = uuid4()
	usage.user_id = user_id or uuid4()
	usage.tenant_id = uuid4()
	usage.period_start = period_start
	usage.period_end = period_start
	usage.episodes_created = episodes_created
	usage.api_calls = api_calls
	usage.storage_bytes = storage_bytes
	usage.overage_cost = Decimal(str(overage_cost))
	usage.compute_hours = 0.0
	usage.overage_episodes = 0
	usage.overage_storage_gb = 0.0
	return usage


def _make_subscription(user_id=None, tier=SubscriptionTier.FREE):
	sub = BillingSubscription()
	sub.id = uuid4()
	sub.user_id = user_id or uuid4()
	sub.tenant_id = uuid4()
	sub.tier = tier
	sub.status = "active"
	sub.auto_renew = True
	sub.currency = "USD"
	sub.price_monthly = Decimal("0")
	sub.created_at = datetime.utcnow()
	sub.updated_at = datetime.utcnow()
	return sub


# ---------------------------------------------------------------------------
# usage_service tests
# ---------------------------------------------------------------------------

class TestCurrentPeriodDates:
	def test_returns_first_of_month(self):
		start, end = _current_period_dates()
		assert start.day == 1
		assert start <= date.today()

	def test_end_is_after_start(self):
		start, end = _current_period_dates()
		assert end > start


class TestCheckEpisodeLimit:
	@pytest.mark.asyncio
	async def test_under_limit_returns_true(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage = _make_usage(user_id=user_id, episodes_created=3)
		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = usage

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		result = await check_episode_limit(db, user_id)
		assert result is True

	@pytest.mark.asyncio
	async def test_at_limit_returns_false(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage = _make_usage(user_id=user_id, episodes_created=5)
		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = usage

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		result = await check_episode_limit(db, user_id)
		assert result is False

	@pytest.mark.asyncio
	async def test_enterprise_unlimited_always_true(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.ENTERPRISE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		db.execute = AsyncMock(return_value=sub_result)

		result = await check_episode_limit(db, user_id)
		assert result is True

	@pytest.mark.asyncio
	async def test_no_usage_record_returns_true(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = None

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		result = await check_episode_limit(db, user_id)
		assert result is True


class TestCheckApiLimit:
	@pytest.mark.asyncio
	async def test_under_limit_returns_true(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage = _make_usage(user_id=user_id, api_calls=50)
		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = usage

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		result = await check_api_limit(db, user_id)
		assert result is True

	@pytest.mark.asyncio
	async def test_at_api_limit_returns_false(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage = _make_usage(user_id=user_id, api_calls=100)
		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = usage

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		result = await check_api_limit(db, user_id)
		assert result is False


class TestCalculateOverageCost:
	@pytest.mark.asyncio
	async def test_no_usage_returns_zero(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = None

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		cost = await calculate_overage_cost(
			db, user_id, date.today().replace(day=1), date.today()
		)
		assert cost == 0.0

	@pytest.mark.asyncio
	async def test_episode_overage_cost(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		# 8 episodes on free plan (limit 5) → 3 overage × $2 = $6
		usage = _make_usage(user_id=user_id, episodes_created=8)
		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = usage

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		cost = await calculate_overage_cost(
			db, user_id, date.today().replace(day=1), date.today()
		)
		assert cost == 6.0

	@pytest.mark.asyncio
	async def test_enterprise_no_overage(self):
		user_id = uuid4()
		db = AsyncMock()

		sub = _make_subscription(user_id=user_id, tier=SubscriptionTier.ENTERPRISE)
		sub_result = MagicMock()
		sub_result.scalar_one_or_none.return_value = sub

		usage = _make_usage(user_id=user_id, episodes_created=10000)
		usage_result = MagicMock()
		usage_result.scalar_one_or_none.return_value = usage

		db.execute = AsyncMock(side_effect=[sub_result, usage_result])

		cost = await calculate_overage_cost(
			db, user_id, date.today().replace(day=1), date.today()
		)
		assert cost == 0.0


# ---------------------------------------------------------------------------
# billing_service tests
# ---------------------------------------------------------------------------

class TestGetOrCreateSubscription:
	@pytest.mark.asyncio
	async def test_returns_existing_subscription(self):
		user_id = uuid4()
		tenant_id = uuid4()
		db = AsyncMock()

		existing = _make_subscription(user_id=user_id)
		result_mock = MagicMock()
		result_mock.scalar_one_or_none.return_value = existing

		db.execute = AsyncMock(return_value=result_mock)

		sub = await get_or_create_subscription(db, user_id, tenant_id)
		assert sub is existing
		db.add.assert_not_called()

	@pytest.mark.asyncio
	async def test_creates_free_subscription_if_none(self):
		user_id = uuid4()
		tenant_id = uuid4()
		db = AsyncMock()

		result_mock = MagicMock()
		result_mock.scalar_one_or_none.return_value = None

		db.execute = AsyncMock(return_value=result_mock)

		sub = await get_or_create_subscription(db, user_id, tenant_id)
		assert sub.tier == SubscriptionTier.FREE
		assert sub.user_id == user_id
		db.add.assert_called_once_with(sub)
		db.flush.assert_called_once()


class TestUpdateSubscriptionTier:
	@pytest.mark.asyncio
	async def test_upgrade_to_pro(self):
		user_id = uuid4()
		tenant_id = uuid4()
		db = AsyncMock()

		existing = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		result_mock = MagicMock()
		result_mock.scalar_one_or_none.return_value = existing

		db.execute = AsyncMock(return_value=result_mock)

		sub = await update_subscription_tier(db, user_id, tenant_id, "pro")
		assert sub.tier == "pro"
		assert sub.price_monthly == 29
		db.flush.assert_called()

	@pytest.mark.asyncio
	async def test_invalid_tier_raises_400(self):
		from fastapi import HTTPException

		user_id = uuid4()
		tenant_id = uuid4()
		db = AsyncMock()

		with pytest.raises(HTTPException) as exc_info:
			await update_subscription_tier(db, user_id, tenant_id, "invalid")
		assert exc_info.value.status_code == 400


class TestCancelSubscription:
	@pytest.mark.asyncio
	async def test_cancel_pro_at_period_end(self):
		user_id = uuid4()
		tenant_id = uuid4()
		db = AsyncMock()

		existing = _make_subscription(user_id=user_id, tier=SubscriptionTier.PRO)
		existing.price_monthly = Decimal("29")
		result_mock = MagicMock()
		result_mock.scalar_one_or_none.return_value = existing

		db.execute = AsyncMock(return_value=result_mock)

		sub = await cancel_subscription(db, user_id, tenant_id, at_period_end=True)
		assert sub.auto_renew is False
		assert sub.status == "active"  # Still active until period ends

	@pytest.mark.asyncio
	async def test_cancel_free_raises_400(self):
		from fastapi import HTTPException

		user_id = uuid4()
		tenant_id = uuid4()
		db = AsyncMock()

		existing = _make_subscription(user_id=user_id, tier=SubscriptionTier.FREE)
		result_mock = MagicMock()
		result_mock.scalar_one_or_none.return_value = existing

		db.execute = AsyncMock(return_value=result_mock)

		with pytest.raises(HTTPException) as exc_info:
			await cancel_subscription(db, user_id, tenant_id)
		assert exc_info.value.status_code == 400
