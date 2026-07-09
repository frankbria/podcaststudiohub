"""
Unit tests for usage_service.py — uses AsyncMock for DB, no real DB needed.

Tests cover:
- _current_period_dates: month-start and next-month-start calculations
- _get_user_tier: no subscription defaults to 'free', returns tier from record
- check_episode_limit: free tier under/at limit, enterprise unlimited
- check_api_limit: under limit returns True, at limit returns False
- get_usage_summary: structure and fields present
- calculate_overage_cost: no usage, episode overage, storage overage
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
	"""Return an AsyncMock that looks like an AsyncSession."""
	db = AsyncMock()
	# db.execute(...) returns an object with scalar_one_or_none
	result = MagicMock()
	result.scalar_one_or_none.return_value = None
	db.execute.return_value = result
	return db


def _make_usage(episodes_created=0, api_calls=0, storage_bytes=0):
	"""Return a MagicMock that looks like a BillingUsage record."""
	usage = MagicMock()
	usage.episodes_created = episodes_created
	usage.api_calls = api_calls
	usage.storage_bytes = storage_bytes
	usage.period_start = date.today().replace(day=1)
	return usage


def _make_subscription(tier: str):
	"""Return a MagicMock that looks like a BillingSubscription record."""
	sub = MagicMock()
	sub.tier = tier
	return sub


# ---------------------------------------------------------------------------
# _current_period_dates
# ---------------------------------------------------------------------------

class TestCurrentPeriodDates:
	def test_start_is_first_of_current_month(self):
		from src.services.usage_service import _current_period_dates
		start, _ = _current_period_dates()
		assert start.day == 1
		assert start.month == date.today().month
		assert start.year == date.today().year

	def test_end_is_first_of_next_month(self):
		from src.services.usage_service import _current_period_dates
		_, end = _current_period_dates()
		today = date.today()
		if today.month == 12:
			assert end.year == today.year + 1
			assert end.month == 1
		else:
			assert end.month == today.month + 1
		assert end.day == 1


# ---------------------------------------------------------------------------
# _get_user_tier
# ---------------------------------------------------------------------------

class TestGetUserTier:
	@pytest.mark.asyncio
	async def test_no_subscription_defaults_to_free(self):
		from src.services.usage_service import _get_user_tier
		db = _mock_db()
		db.execute.return_value.scalar_one_or_none.return_value = None

		tier = await _get_user_tier(db, uuid4())
		assert tier == "free"

	@pytest.mark.asyncio
	async def test_returns_subscription_tier(self):
		from src.services.usage_service import _get_user_tier
		db = _mock_db()
		db.execute.return_value.scalar_one_or_none.return_value = _make_subscription("pro")

		tier = await _get_user_tier(db, uuid4())
		assert tier == "pro"

	@pytest.mark.asyncio
	async def test_enterprise_tier_returned(self):
		from src.services.usage_service import _get_user_tier
		db = _mock_db()
		db.execute.return_value.scalar_one_or_none.return_value = _make_subscription("enterprise")

		tier = await _get_user_tier(db, uuid4())
		assert tier == "enterprise"


# ---------------------------------------------------------------------------
# check_episode_limit
# ---------------------------------------------------------------------------

class TestCheckEpisodeLimit:
	@pytest.mark.asyncio
	async def test_free_tier_under_limit_returns_true(self):
		"""Free tier has 5 episodes/month limit; 3 created → allowed."""
		from src.services.usage_service import check_episode_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_usage(episodes_created=3))),
		]
		db.execute.side_effect = results

		result = await check_episode_limit(db, uuid4())
		assert result is True

	@pytest.mark.asyncio
	async def test_free_tier_at_limit_returns_false(self):
		"""Free tier has 5 episodes/month limit; 5 created → denied."""
		from src.services.usage_service import check_episode_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_usage(episodes_created=5))),
		]
		db.execute.side_effect = results

		result = await check_episode_limit(db, uuid4())
		assert result is False

	@pytest.mark.asyncio
	async def test_enterprise_tier_is_unlimited(self):
		"""Enterprise tier has no episodes limit → always True."""
		from src.services.usage_service import check_episode_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("enterprise"))),
		]
		db.execute.side_effect = results

		result = await check_episode_limit(db, uuid4())
		assert result is True

	@pytest.mark.asyncio
	async def test_no_usage_record_counts_as_zero(self):
		"""If no usage record exists, count is 0 → allowed for free tier."""
		from src.services.usage_service import check_episode_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
		]
		db.execute.side_effect = results

		result = await check_episode_limit(db, uuid4())
		assert result is True


# ---------------------------------------------------------------------------
# check_api_limit
# ---------------------------------------------------------------------------

class TestCheckApiLimit:
	@pytest.mark.asyncio
	async def test_under_limit_returns_true(self):
		from src.services.usage_service import check_api_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_usage(api_calls=100))),
		]
		db.execute.side_effect = results

		result = await check_api_limit(db, uuid4())
		assert result is True

	@pytest.mark.asyncio
	async def test_at_limit_returns_false(self):
		"""Free tier 3000 api_calls/month; 3000 calls → denied."""
		from src.services.usage_service import check_api_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_usage(api_calls=3000))),
		]
		db.execute.side_effect = results

		result = await check_api_limit(db, uuid4())
		assert result is False

	@pytest.mark.asyncio
	async def test_enterprise_unlimited_always_true(self):
		from src.services.usage_service import check_api_limit
		db = _mock_db()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("enterprise"))),
		]
		db.execute.side_effect = results

		result = await check_api_limit(db, uuid4())
		assert result is True


# ---------------------------------------------------------------------------
# get_usage_summary
# ---------------------------------------------------------------------------

class TestGetUsageSummary:
	@pytest.mark.asyncio
	async def test_returns_expected_keys(self):
		from src.services.usage_service import get_usage_summary
		db = _mock_db()
		usage = _make_usage(episodes_created=2, api_calls=50, storage_bytes=1024)

		# _get_user_tier (select), then _get_or_create_usage:
		# upsert insert (on_conflict_do_nothing) + re-select via scalar_one().
		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(),  # ON CONFLICT DO NOTHING insert
			MagicMock(scalar_one=MagicMock(return_value=usage)),
		]
		db.execute.side_effect = results

		summary = await get_usage_summary(db, uuid4(), uuid4())

		assert "episodes_created" in summary
		assert "episodes_limit" in summary
		assert "storage_bytes" in summary
		assert "api_calls" in summary
		assert "api_calls_limit" in summary

	@pytest.mark.asyncio
	async def test_free_tier_limits_are_populated(self):
		from src.services.usage_service import get_usage_summary
		db = _mock_db()
		usage = _make_usage(episodes_created=1, api_calls=10, storage_bytes=512)

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(),  # ON CONFLICT DO NOTHING insert
			MagicMock(scalar_one=MagicMock(return_value=usage)),
		]
		db.execute.side_effect = results

		summary = await get_usage_summary(db, uuid4(), uuid4())

		assert summary["episodes_limit"] == 5
		assert summary["api_calls_limit"] == 3000


# ---------------------------------------------------------------------------
# calculate_overage_cost
# ---------------------------------------------------------------------------

class TestCalculateOverageCost:
	@pytest.mark.asyncio
	async def test_no_usage_record_returns_zero(self):
		from src.services.usage_service import calculate_overage_cost
		db = _mock_db()
		today = date.today()

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
		]
		db.execute.side_effect = results

		cost = await calculate_overage_cost(
			db, uuid4(), today.replace(day=1), today
		)
		assert cost == Decimal("0")

	@pytest.mark.asyncio
	async def test_episode_overage_produces_positive_cost(self):
		"""10 episodes over limit of 5 → positive cost."""
		from src.services.usage_service import calculate_overage_cost
		db = _mock_db()
		today = date.today()
		usage = _make_usage(episodes_created=10, storage_bytes=0)

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=usage)),
		]
		db.execute.side_effect = results

		cost = await calculate_overage_cost(
			db, uuid4(), today.replace(day=1), today
		)
		# 5 episodes over limit × $2.00/episode = $10.00
		assert cost > Decimal("0")
		assert cost == Decimal("10.00")

	@pytest.mark.asyncio
	async def test_storage_overage_produces_positive_cost(self):
		"""2 GB storage with 1 GB limit → $0.50 overage."""
		from src.services.usage_service import calculate_overage_cost
		db = _mock_db()
		today = date.today()
		# 2 GB in bytes
		usage = _make_usage(episodes_created=0, storage_bytes=2 * (1024 ** 3))

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("free"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=usage)),
		]
		db.execute.side_effect = results

		cost = await calculate_overage_cost(
			db, uuid4(), today.replace(day=1), today
		)
		# 1 GB over 1 GB limit × $0.50/GB = $0.50
		assert cost > Decimal("0")

	@pytest.mark.asyncio
	async def test_enterprise_no_overage(self):
		"""Enterprise has unlimited storage and episodes → zero overage."""
		from src.services.usage_service import calculate_overage_cost
		db = _mock_db()
		today = date.today()
		usage = _make_usage(episodes_created=1000, storage_bytes=1000 * (1024 ** 3))

		results = [
			MagicMock(scalar_one_or_none=MagicMock(return_value=_make_subscription("enterprise"))),
			MagicMock(scalar_one_or_none=MagicMock(return_value=usage)),
		]
		db.execute.side_effect = results

		cost = await calculate_overage_cost(
			db, uuid4(), today.replace(day=1), today
		)
		assert cost == Decimal("0")
