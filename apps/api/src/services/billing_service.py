"""Billing service for Stripe payment integration and subscription management"""

import logging
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing_pricing import PRICING_TIERS, get_tier_price
from ..models.billing_subscription import (
	BillingSubscription,
	SubscriptionStatus,
	SubscriptionTier,
)

logger = logging.getLogger(__name__)


async def get_or_create_subscription(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
) -> BillingSubscription:
	"""Get existing subscription or create a default free-tier one.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID

	Returns:
		BillingSubscription instance
	"""
	result = await db.execute(
		select(BillingSubscription).where(BillingSubscription.user_id == user_id)
	)
	subscription = result.scalar_one_or_none()

	if subscription is None:
		subscription = BillingSubscription(
			user_id=user_id,
			tenant_id=tenant_id,
			tier=SubscriptionTier.FREE,
			status=SubscriptionStatus.ACTIVE,
			price_monthly=0,
		)
		db.add(subscription)
		await db.flush()

	return subscription


async def create_checkout_session(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	tier: str,
	return_url: str,
) -> Dict[str, str]:
	"""Create a Stripe Checkout session for a subscription upgrade.

	In production this would call the Stripe API. Currently returns a mock
	checkout URL for development/testing when Stripe is not configured.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
		tier: Target subscription tier
		return_url: URL to redirect to after checkout

	Returns:
		Dict with checkout_url key

	Raises:
		HTTPException: 400 if tier is invalid or already subscribed
	"""
	if tier not in PRICING_TIERS:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid tier: {tier}. Must be one of {list(PRICING_TIERS.keys())}",
		)

	if tier == SubscriptionTier.FREE:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Cannot checkout for the free tier. Use PATCH /billing/subscription to downgrade.",
		)

	subscription = await get_or_create_subscription(db, user_id, tenant_id)

	if subscription.tier == tier:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Already subscribed to {tier} tier.",
		)

	try:
		import stripe
		from ..config import settings

		if not getattr(settings, "STRIPE_SECRET_KEY", None):
			raise ImportError("No Stripe key")

		stripe.api_key = settings.STRIPE_SECRET_KEY

		# Look up or create Stripe customer
		if subscription.stripe_customer_id:
			customer_id = subscription.stripe_customer_id
		else:
			# In a real implementation you would fetch the user's email here
			customer = stripe.Customer.create(metadata={"user_id": str(user_id)})
			customer_id = customer.id
			subscription.stripe_customer_id = customer_id
			await db.flush()

		price_id = _get_stripe_price_id(tier)
		session = stripe.checkout.Session.create(
			customer=customer_id,
			payment_method_types=["card"],
			mode="subscription",
			line_items=[{"price": price_id, "quantity": 1}],
			success_url=f"{return_url}?session_id={{CHECKOUT_SESSION_ID}}",
			cancel_url=return_url,
			metadata={"user_id": str(user_id), "tier": tier},
		)
		return {"checkout_url": session.url}

	except (ImportError, Exception) as exc:
		# Stripe not configured — return a placeholder URL for dev/test
		logger.warning("Stripe not configured or error occurred: %s", exc)
		return {
			"checkout_url": f"{return_url}?mock=true&tier={tier}&user_id={user_id}"
		}


def _get_stripe_price_id(tier: str) -> str:
	"""Get Stripe Price ID for a tier (reads from settings if available)."""
	try:
		from ..config import settings

		attr = f"STRIPE_PRICE_{tier.upper()}"
		price_id = getattr(settings, attr, None)
		if price_id:
			return price_id
	except Exception:
		pass
	return f"price_{tier}_monthly"


async def update_subscription_tier(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	new_tier: str,
) -> BillingSubscription:
	"""Upgrade or downgrade a subscription tier.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
		new_tier: Target tier name

	Returns:
		Updated BillingSubscription

	Raises:
		HTTPException: 400 if tier is invalid
	"""
	if new_tier not in PRICING_TIERS:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid tier: {new_tier}.",
		)

	subscription = await get_or_create_subscription(db, user_id, tenant_id)
	subscription.tier = new_tier
	subscription.price_monthly = get_tier_price(new_tier)
	subscription.status = SubscriptionStatus.ACTIVE
	subscription.updated_at = datetime.utcnow()

	if new_tier == SubscriptionTier.FREE:
		subscription.stripe_subscription_id = None
		subscription.billing_cycle_start = None
		subscription.billing_cycle_end = None
		subscription.renewal_date = None

	await db.flush()
	return subscription


async def cancel_subscription(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	at_period_end: bool = True,
) -> BillingSubscription:
	"""Cancel a subscription.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
		at_period_end: If True, cancel at end of billing period; if False, immediately

	Returns:
		Updated BillingSubscription
	"""
	subscription = await get_or_create_subscription(db, user_id, tenant_id)

	if subscription.tier == SubscriptionTier.FREE:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Free tier subscriptions cannot be canceled.",
		)

	if at_period_end:
		subscription.auto_renew = False
		subscription.status = SubscriptionStatus.ACTIVE  # Still active until period end
	else:
		subscription.status = SubscriptionStatus.CANCELED
		subscription.canceled_at = datetime.utcnow()
		subscription.tier = SubscriptionTier.FREE
		subscription.price_monthly = 0

	subscription.updated_at = datetime.utcnow()
	await db.flush()
	return subscription


async def process_stripe_webhook(
	db: AsyncSession,
	event_type: str,
	event_data: Dict[str, Any],
) -> None:
	"""Process incoming Stripe webhook events.

	Handles subscription lifecycle events and updates local subscription records.

	Args:
		db: Database session
		event_type: Stripe event type string
		event_data: Event data object from Stripe
	"""
	obj = event_data.get("object", {})

	if event_type == "customer.subscription.updated":
		await _handle_subscription_updated(db, obj)
	elif event_type == "customer.subscription.deleted":
		await _handle_subscription_deleted(db, obj)
	elif event_type == "invoice.payment_succeeded":
		await _handle_payment_succeeded(db, obj)
	elif event_type == "invoice.payment_failed":
		await _handle_payment_failed(db, obj)
	else:
		logger.debug("Unhandled Stripe event type: %s", event_type)


async def _handle_subscription_updated(
	db: AsyncSession,
	obj: Dict[str, Any],
) -> None:
	stripe_sub_id = obj.get("id")
	stripe_status = obj.get("status")
	metadata = obj.get("metadata", {})
	tier = metadata.get("tier")

	if not stripe_sub_id:
		return

	result = await db.execute(
		select(BillingSubscription).where(
			BillingSubscription.stripe_subscription_id == stripe_sub_id
		)
	)
	subscription = result.scalar_one_or_none()
	if subscription is None:
		return

	if stripe_status:
		status_map = {
			"active": SubscriptionStatus.ACTIVE,
			"past_due": SubscriptionStatus.PAST_DUE,
			"canceled": SubscriptionStatus.CANCELED,
			"paused": SubscriptionStatus.PAUSED,
			"trialing": SubscriptionStatus.TRIALING,
		}
		subscription.status = status_map.get(stripe_status, subscription.status)

	if tier and tier in PRICING_TIERS:
		subscription.tier = tier
		subscription.price_monthly = get_tier_price(tier)

	# Update billing cycle dates from Stripe period
	current_period_start = obj.get("current_period_start")
	current_period_end = obj.get("current_period_end")
	if current_period_start:
		subscription.billing_cycle_start = datetime.utcfromtimestamp(current_period_start)
	if current_period_end:
		subscription.billing_cycle_end = datetime.utcfromtimestamp(current_period_end)
		subscription.renewal_date = datetime.utcfromtimestamp(current_period_end)

	subscription.updated_at = datetime.utcnow()
	await db.flush()


async def _handle_subscription_deleted(
	db: AsyncSession,
	obj: Dict[str, Any],
) -> None:
	stripe_sub_id = obj.get("id")
	if not stripe_sub_id:
		return

	result = await db.execute(
		select(BillingSubscription).where(
			BillingSubscription.stripe_subscription_id == stripe_sub_id
		)
	)
	subscription = result.scalar_one_or_none()
	if subscription is None:
		return

	subscription.status = SubscriptionStatus.CANCELED
	subscription.tier = SubscriptionTier.FREE
	subscription.price_monthly = 0
	subscription.canceled_at = datetime.utcnow()
	subscription.updated_at = datetime.utcnow()
	await db.flush()


async def _handle_payment_succeeded(
	db: AsyncSession,
	obj: Dict[str, Any],
) -> None:
	stripe_sub_id = obj.get("subscription")
	if not stripe_sub_id:
		return

	result = await db.execute(
		select(BillingSubscription).where(
			BillingSubscription.stripe_subscription_id == stripe_sub_id
		)
	)
	subscription = result.scalar_one_or_none()
	if subscription is None:
		return

	subscription.status = SubscriptionStatus.ACTIVE
	subscription.updated_at = datetime.utcnow()
	await db.flush()


async def _handle_payment_failed(
	db: AsyncSession,
	obj: Dict[str, Any],
) -> None:
	stripe_sub_id = obj.get("subscription")
	if not stripe_sub_id:
		return

	result = await db.execute(
		select(BillingSubscription).where(
			BillingSubscription.stripe_subscription_id == stripe_sub_id
		)
	)
	subscription = result.scalar_one_or_none()
	if subscription is None:
		return

	subscription.status = SubscriptionStatus.PAST_DUE
	subscription.updated_at = datetime.utcnow()
	await db.flush()
