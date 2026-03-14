"""Usage tracking service for billing period enforcement and overage calculation"""

from datetime import date, datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing_pricing import OVERAGE_PRICING, get_tier_features, is_unlimited
from ..models.billing_subscription import BillingSubscription, SubscriptionTier
from ..models.billing_usage import BillingUsage


def _current_period_dates() -> tuple[date, date]:
	"""Return (period_start, period_end) for the current calendar month."""
	today = date.today()
	period_start = today.replace(day=1)
	# Last day of month
	if today.month == 12:
		period_end = today.replace(year=today.year + 1, month=1, day=1)
	else:
		period_end = today.replace(month=today.month + 1, day=1)
	return period_start, period_end


async def _get_or_create_usage(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
) -> BillingUsage:
	"""Get or create billing usage record for the current period."""
	period_start, period_end = _current_period_dates()

	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()

	if usage is None:
		usage = BillingUsage(
			user_id=user_id,
			tenant_id=tenant_id,
			period_start=period_start,
			period_end=period_end,
		)
		db.add(usage)
		await db.flush()

	return usage


async def _get_subscription(
	db: AsyncSession,
	user_id: UUID,
) -> Optional[BillingSubscription]:
	"""Get subscription for user."""
	result = await db.execute(
		select(BillingSubscription).where(BillingSubscription.user_id == user_id)
	)
	return result.scalar_one_or_none()


async def _get_user_tier(db: AsyncSession, user_id: UUID) -> str:
	"""Return the user's subscription tier (defaults to 'free')."""
	sub = await _get_subscription(db, user_id)
	if sub is None:
		return SubscriptionTier.FREE
	return sub.tier


async def track_episode_creation(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
) -> None:
	"""Increment episode count for the current billing period.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
	"""
	usage = await _get_or_create_usage(db, user_id, tenant_id)
	usage.episodes_created += 1
	usage.updated_at = datetime.utcnow()
	await db.flush()


async def track_api_call(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
) -> None:
	"""Track an API call for the current billing period.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
	"""
	usage = await _get_or_create_usage(db, user_id, tenant_id)
	usage.api_calls += 1
	usage.updated_at = datetime.utcnow()
	await db.flush()


async def update_storage_bytes(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	bytes_delta: int,
) -> None:
	"""Update cumulative storage for the current billing period.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
		bytes_delta: Bytes to add (positive) or subtract (negative)
	"""
	usage = await _get_or_create_usage(db, user_id, tenant_id)
	usage.storage_bytes = max(0, usage.storage_bytes + bytes_delta)
	usage.updated_at = datetime.utcnow()
	await db.flush()


async def check_episode_limit(
	db: AsyncSession,
	user_id: UUID,
) -> bool:
	"""Return True if the user can create another episode in the current period.

	Args:
		db: Database session
		user_id: User ID

	Returns:
		True if under limit, False if limit reached
	"""
	tier = await _get_user_tier(db, user_id)
	features = get_tier_features(tier)
	limit = features.get("episodes_per_month", 5)

	if is_unlimited(limit):
		return True

	period_start, _ = _current_period_dates()
	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()
	if usage is None:
		return True

	return usage.episodes_created < limit


async def check_api_limit(
	db: AsyncSession,
	user_id: UUID,
) -> bool:
	"""Return True if the user is within their daily API call limit.

	Args:
		db: Database session
		user_id: User ID

	Returns:
		True if under limit, False if limit reached
	"""
	tier = await _get_user_tier(db, user_id)
	features = get_tier_features(tier)
	limit = features.get("api_calls_per_day", 100)

	if is_unlimited(limit):
		return True

	period_start, _ = _current_period_dates()
	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()
	if usage is None:
		return True

	return usage.api_calls < limit


async def get_usage_summary(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
) -> Dict[str, Any]:
	"""Get usage summary for the current billing period.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID

	Returns:
		Dict with usage metrics and tier limits
	"""
	tier = await _get_user_tier(db, user_id)
	features = get_tier_features(tier)
	period_start, period_end = _current_period_dates()

	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()

	episodes_created = usage.episodes_created if usage else 0
	api_calls = usage.api_calls if usage else 0
	storage_bytes = usage.storage_bytes if usage else 0

	episodes_limit = features.get("episodes_per_month", 5)
	storage_limit_gb = features.get("storage_gb", 1)
	api_calls_limit = features.get("api_calls_per_day", 100)

	storage_limit_bytes = (
		None if is_unlimited(storage_limit_gb) else int(storage_limit_gb * 1024 ** 3)
	)
	episodes_limit_val = None if is_unlimited(episodes_limit) else episodes_limit
	api_calls_limit_val = None if is_unlimited(api_calls_limit) else api_calls_limit

	return {
		"period": {
			"start": period_start.isoformat(),
			"end": period_end.isoformat(),
		},
		"usage": {
			"episodes": {
				"count": episodes_created,
				"limit": episodes_limit_val,
				"percent": (
					round(episodes_created / episodes_limit_val * 100)
					if episodes_limit_val
					else None
				),
			},
			"storage": {
				"bytes": storage_bytes,
				"limit_bytes": storage_limit_bytes,
				"gb": round(storage_bytes / 1024 ** 3, 3),
				"limit_gb": None if is_unlimited(storage_limit_gb) else storage_limit_gb,
				"percent": (
					round(storage_bytes / storage_limit_bytes * 100)
					if storage_limit_bytes
					else None
				),
			},
			"api_calls": {
				"count": api_calls,
				"limit": api_calls_limit_val,
				"percent": (
					round(api_calls / api_calls_limit_val * 100)
					if api_calls_limit_val
					else None
				),
			},
		},
		"overage_charges": {
			"total": float(usage.overage_cost) if usage else 0.0,
			"line_items": [],
		},
	}


async def calculate_overage_cost(
	db: AsyncSession,
	user_id: UUID,
	period_start: date,
	period_end: date,
) -> float:
	"""Calculate overage charges for a billing period.

	Args:
		db: Database session
		user_id: User ID
		period_start: Start of billing period
		period_end: End of billing period

	Returns:
		Total overage cost in USD
	"""
	tier = await _get_user_tier(db, user_id)
	features = get_tier_features(tier)

	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()
	if usage is None:
		return 0.0

	total_cost = 0.0

	# Episode overages
	episodes_limit = features.get("episodes_per_month", 5)
	if not is_unlimited(episodes_limit):
		overage_episodes = max(0, usage.episodes_created - episodes_limit)
		total_cost += overage_episodes * float(OVERAGE_PRICING["cost_per_episode_over_limit"])

	# Storage overages
	storage_limit_gb = features.get("storage_gb", 1)
	if not is_unlimited(storage_limit_gb):
		storage_gb = usage.storage_bytes / 1024 ** 3
		overage_gb = max(0.0, storage_gb - float(storage_limit_gb))
		total_cost += overage_gb * float(OVERAGE_PRICING["cost_per_gb_per_month"])

	return round(total_cost, 2)
