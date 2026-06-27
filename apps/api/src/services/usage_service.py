"""Usage tracking service for billing enforcement"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.billing_subscription import BillingSubscription
from ..models.billing_usage import BillingUsage
from ..utils.pricing import OVERAGE_PRICING, get_tier_limit, is_unlimited


def _current_period_dates() -> tuple[date, date]:
	"""Return the (start, end) of the current calendar month."""
	today = date.today()
	start = today.replace(day=1)
	# period_end is the first day of the next month (exclusive upper bound)
	if today.month == 12:
		end = today.replace(year=today.year + 1, month=1, day=1)
	else:
		end = today.replace(month=today.month + 1, day=1)
	return start, end


async def _get_or_create_usage(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> BillingUsage:
	"""Return usage record for the current period, creating one if needed."""
	period_start, period_end = _current_period_dates()

	# Concurrency-safe first-touch insert: ON CONFLICT DO NOTHING means two
	# concurrent requests for the same (user_id, period_start) can never create
	# duplicate rows. Metric columns rely on their DB defaults.
	await db.execute(
		pg_insert(BillingUsage)
		.values(
			user_id=user_id,
			tenant_id=tenant_id,
			period_start=period_start,
			period_end=period_end,
		)
		.on_conflict_do_nothing(index_elements=["user_id", "period_start"])
	)

	# Re-select the guaranteed-present row (either ours or the concurrent winner's).
	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	return result.scalar_one()


async def _get_user_tier(db: AsyncSession, user_id: UUID) -> str:
	"""Return the user's current subscription tier (defaults to 'free')."""
	result = await db.execute(
		select(BillingSubscription).where(BillingSubscription.user_id == user_id)
	)
	sub = result.scalar_one_or_none()
	if sub is None:
		return "free"
	return sub.tier


async def track_episode_creation(
	db: AsyncSession, user_id: UUID, tenant_id: UUID, count: int = 1
) -> None:
	"""Increment episode count for current billing period (by ``count``)."""
	if count <= 0:
		return
	await _get_or_create_usage(db, user_id, tenant_id)
	period_start, _ = _current_period_dates()
	# Atomic server-side increment avoids lost updates under concurrency.
	await db.execute(
		update(BillingUsage)
		.where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
		.values(
			episodes_created=BillingUsage.episodes_created + count,
			updated_at=datetime.utcnow(),
		)
	)
	await db.commit()


async def track_api_call(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> None:
	"""Track an API call for the current billing period."""
	await _get_or_create_usage(db, user_id, tenant_id)
	period_start, _ = _current_period_dates()
	# Atomic server-side increment avoids lost updates under concurrency.
	await db.execute(
		update(BillingUsage)
		.where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
		.values(
			api_calls=BillingUsage.api_calls + 1,
			updated_at=datetime.utcnow(),
		)
	)
	await db.commit()


async def check_episode_quota(db: AsyncSession, user_id: UUID, count: int = 1) -> bool:
	"""Return True if ``count`` more episodes fit within this period's limit."""
	tier = await _get_user_tier(db, user_id)
	if is_unlimited(tier, "episodes_per_month"):
		return True

	limit = get_tier_limit(tier, "episodes_per_month")
	period_start, _ = _current_period_dates()

	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()
	current = usage.episodes_created if usage else 0
	return current + count <= limit


async def check_episode_limit(db: AsyncSession, user_id: UUID) -> bool:
	"""Return True if user can create another episode this period."""
	return await check_episode_quota(db, user_id, 1)


async def check_api_limit(db: AsyncSession, user_id: UUID) -> bool:
	"""Return True if user is within API call limits this period."""
	tier = await _get_user_tier(db, user_id)
	if is_unlimited(tier, "api_calls_per_month"):
		return True

	limit = get_tier_limit(tier, "api_calls_per_month")
	period_start, _ = _current_period_dates()

	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()
	current = usage.api_calls if usage else 0
	return current < limit


async def get_usage_summary(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
	"""Return usage summary for the current billing period."""
	tier = await _get_user_tier(db, user_id)
	usage = await _get_or_create_usage(db, user_id, tenant_id)

	episodes_limit = get_tier_limit(tier, "episodes_per_month")
	storage_limit_gb = get_tier_limit(tier, "storage_gb")
	storage_limit_bytes = int(storage_limit_gb * 1024 ** 3) if storage_limit_gb is not None else None
	api_limit = get_tier_limit(tier, "api_calls_per_month")

	return {
		"episodes_created": usage.episodes_created,
		"episodes_limit": episodes_limit,
		"storage_bytes": usage.storage_bytes,
		"storage_limit_bytes": storage_limit_bytes,
		"api_calls": usage.api_calls,
		"api_calls_limit": api_limit,
	}


async def calculate_overage_cost(
	db: AsyncSession,
	user_id: UUID,
	period_start: date,
	period_end: date,
) -> Decimal:
	"""Calculate overage charges for a specific period."""
	tier = await _get_user_tier(db, user_id)

	result = await db.execute(
		select(BillingUsage).where(
			BillingUsage.user_id == user_id,
			BillingUsage.period_start == period_start,
		)
	)
	usage = result.scalar_one_or_none()
	if usage is None:
		return Decimal("0")

	total = Decimal("0")
	episode_limit = get_tier_limit(tier, "episodes_per_month")
	if episode_limit is not None and usage.episodes_created > episode_limit:
		overage = usage.episodes_created - episode_limit
		total += Decimal(str(OVERAGE_PRICING["cost_per_episode_over_limit"])) * overage

	storage_limit_gb = get_tier_limit(tier, "storage_gb")
	if storage_limit_gb is not None:
		used_gb = usage.storage_bytes / (1024 ** 3)
		if used_gb > storage_limit_gb:
			overage_gb = used_gb - storage_limit_gb
			total += Decimal(str(OVERAGE_PRICING["cost_per_gb_per_month"])) * Decimal(str(round(overage_gb, 4)))

	return total
