"""Billing service: Stripe integration and subscription management"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import arm_tenant_context, set_tenant_context
from ..models.billing_subscription import BillingSubscription, SubscriptionStatus, SubscriptionTier
from ..utils.pricing import PRICING_TIERS
from ..utils.datetime_utils import utcnow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stripe import — optional dependency; fall back to mock mode if not installed
# ---------------------------------------------------------------------------
try:
	import stripe as _stripe_module
	_STRIPE_AVAILABLE = True
except ImportError:
	_stripe_module = None  # type: ignore[assignment]
	_STRIPE_AVAILABLE = False


def _get_stripe_key() -> Optional[str]:
	"""Return the configured Stripe secret key, or None."""
	try:
		from ..config import settings  # type: ignore[import]
		return getattr(settings, "STRIPE_SECRET_KEY", None)
	except Exception:
		return None


def _stripe_enabled() -> bool:
	"""Return True when Stripe is available and a secret key is configured."""
	return _STRIPE_AVAILABLE and bool(_get_stripe_key())


# ---------------------------------------------------------------------------
# Subscription helpers
# ---------------------------------------------------------------------------


async def get_or_create_subscription(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> BillingSubscription:
	"""Return the user's subscription record, creating a free-tier one if absent."""
	result = await db.execute(
		select(BillingSubscription).where(BillingSubscription.user_id == user_id)
	)
	sub = result.scalar_one_or_none()
	if sub is None:
		sub = BillingSubscription(
			user_id=user_id,
			tenant_id=tenant_id,
			tier=SubscriptionTier.FREE,
			status=SubscriptionStatus.ACTIVE,
		)
		db.add(sub)
		await db.commit()
		await db.refresh(sub)
	return sub


async def get_subscription(db: AsyncSession, user_id: UUID) -> Optional[BillingSubscription]:
	"""Return subscription for a user, or None."""
	result = await db.execute(
		select(BillingSubscription).where(BillingSubscription.user_id == user_id)
	)
	return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


async def create_checkout_session(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	tier: str,
	return_url: Optional[str] = None,
) -> Dict[str, str]:
	"""Create a Stripe Checkout session (or mock URL when Stripe not configured)."""
	if tier not in ("pro", "enterprise"):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid tier for checkout: {tier}",
		)

	sub = await get_or_create_subscription(db, user_id, tenant_id)

	if not _stripe_enabled():
		# In production a mock URL would send paying users to a dead link, so
		# signal billing is disabled instead. The mock URL is dev/test only (issue #298).
		from ..config import settings  # type: ignore[import]
		if settings.is_production:
			raise HTTPException(
				status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
				detail="Billing is not configured; upgrades are currently unavailable.",
			)
		mock_url = f"https://checkout.stripe.com/mock?tier={tier}&user={user_id}"
		logger.info("Stripe not configured; returning mock checkout URL")
		return {"checkout_url": mock_url}

	# Real Stripe mode
	_stripe_module.api_key = _get_stripe_key()  # type: ignore[union-attr]
	tier_config = PRICING_TIERS.get(tier, {})
	price_monthly = tier_config.get("price_monthly")
	if price_monthly is None:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Enterprise tier requires custom pricing; contact sales.",
		)

	# Ensure Stripe customer exists
	customer_id = sub.stripe_customer_id
	if not customer_id:
		customer = _stripe_module.Customer.create(metadata={"user_id": str(user_id)})  # type: ignore[union-attr]
		sub.stripe_customer_id = customer.id
		await db.commit()
		customer_id = customer.id

	session = _stripe_module.checkout.Session.create(  # type: ignore[union-attr]
		customer=customer_id,
		mode="subscription",
		line_items=[{
			"price_data": {
				"currency": "usd",
				"unit_amount": int(price_monthly * 100),
				"recurring": {"interval": "month"},
				"product_data": {"name": f"Podcastfy {tier_config['name']}"},
			},
			"quantity": 1,
		}],
		success_url=return_url or "http://localhost:3000/billing/success",
		cancel_url=return_url or "http://localhost:3000/billing/cancel",
		metadata={"user_id": str(user_id), "tier": tier},
	)
	return {"checkout_url": session.url}


# ---------------------------------------------------------------------------
# Subscription management
# ---------------------------------------------------------------------------


async def update_subscription_tier(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	new_tier: str,
) -> BillingSubscription:
	"""Upgrade or downgrade subscription tier."""
	if new_tier not in PRICING_TIERS:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Unknown tier: {new_tier}",
		)

	sub = await get_or_create_subscription(db, user_id, tenant_id)

	tier_config = PRICING_TIERS[new_tier]
	price = tier_config.get("price_monthly")
	sub.tier = new_tier
	sub.price_monthly = Decimal(str(price)) if price is not None else None
	sub.status = SubscriptionStatus.ACTIVE
	sub.updated_at = utcnow()

	await db.commit()
	await db.refresh(sub)
	return sub


async def cancel_subscription(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	at_period_end: bool = True,
) -> BillingSubscription:
	"""Cancel subscription."""
	sub = await get_or_create_subscription(db, user_id, tenant_id)

	if at_period_end:
		sub.auto_renew = False
	else:
		sub.status = SubscriptionStatus.CANCELED
		sub.canceled_at = utcnow()

	sub.updated_at = utcnow()
	await db.commit()
	await db.refresh(sub)
	return sub


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------


async def process_webhook(
	db: AsyncSession,
	payload: bytes,
	sig_header: Optional[str],
	webhook_secret: Optional[str],
) -> Dict[str, Any]:
	"""Process a Stripe webhook event."""
	if not _stripe_enabled():
		logger.info("Stripe not configured; skipping webhook processing")
		return {"status": "ignored", "reason": "stripe_not_configured"}

	_stripe_module.api_key = _get_stripe_key()  # type: ignore[union-attr]

	# Signature verification is mandatory when billing is enabled. There is no
	# unsigned/unverified fallback: a missing secret or signature header is
	# rejected outright rather than parsed, closing the bypass in issue #216.
	if not webhook_secret:
		logger.error(
			"Stripe billing is enabled but STRIPE_WEBHOOK_SECRET is not configured; "
			"rejecting webhook instead of processing it unverified"
		)
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Webhook secret not configured",
		)
	if not sig_header:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Missing webhook signature",
		)

	try:
		event = _stripe_module.Webhook.construct_event(  # type: ignore[union-attr]
			payload, sig_header, webhook_secret
		)
	except _stripe_module.error.SignatureVerificationError:  # type: ignore[union-attr]
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid webhook signature",
		)

	event_type = event.get("type", "")
	data = event.get("data", {}).get("object", {})

	if event_type in ("customer.subscription.updated", "customer.subscription.created"):
		await _handle_subscription_updated(db, data)
	elif event_type == "customer.subscription.deleted":
		await _handle_subscription_deleted(db, data)

	return {"status": "processed", "event_type": event_type}


async def _bootstrap_webhook_tenant(db: AsyncSession, customer_id: Optional[str]) -> bool:
	"""Arm RLS tenant context for a Stripe webhook (no JWT -> no tenant context).

	Resolves stripe_customer_id -> tenant_id through the SECURITY DEFINER
	function from migration 014 (billing_subscriptions is FORCE-RLS'd, so a
	plain SELECT would see nothing), then ARMS app.tenant_id (survives any
	future mid-handler commit — one-shot SET LOCAL would silently drop the
	event after the first commit) so the existing ORM code operates on the
	right tenant's rows. Returns False when the customer matches no
	subscription.
	"""
	if not customer_id:
		return False
	result = await db.execute(
		text("SELECT billing_tenant_for_stripe_customer(:cid)"),
		{"cid": customer_id},
	)
	tenant_id = result.scalar_one_or_none()
	if tenant_id is None:
		return False
	arm_tenant_context(db, str(tenant_id))
	# Arming takes effect at the next transaction begin; set it for the
	# already-open transaction too.
	await set_tenant_context(db, str(tenant_id))
	return True


async def _handle_subscription_updated(db: AsyncSession, subscription_obj: Dict[str, Any]) -> None:
	"""Update local subscription from Stripe data."""
	stripe_sub_id = subscription_obj.get("id")
	customer_id = subscription_obj.get("customer")
	stripe_status = subscription_obj.get("status", "active")

	if not await _bootstrap_webhook_tenant(db, customer_id):
		return

	result = await db.execute(
		select(BillingSubscription).where(
			BillingSubscription.stripe_customer_id == customer_id
		)
	)
	sub = result.scalar_one_or_none()
	if sub is None:
		return

	sub.stripe_subscription_id = stripe_sub_id
	sub.status = _map_stripe_status(stripe_status)
	sub.updated_at = utcnow()
	await db.commit()


async def _handle_subscription_deleted(db: AsyncSession, subscription_obj: Dict[str, Any]) -> None:
	"""Mark subscription as canceled."""
	customer_id = subscription_obj.get("customer")

	if not await _bootstrap_webhook_tenant(db, customer_id):
		return

	result = await db.execute(
		select(BillingSubscription).where(
			BillingSubscription.stripe_customer_id == customer_id
		)
	)
	sub = result.scalar_one_or_none()
	if sub is None:
		return

	sub.status = SubscriptionStatus.CANCELED
	sub.canceled_at = utcnow()
	sub.tier = SubscriptionTier.FREE
	sub.updated_at = utcnow()
	await db.commit()


def _map_stripe_status(stripe_status: str) -> str:
	"""Map Stripe subscription status to local status."""
	mapping = {
		"active": SubscriptionStatus.ACTIVE,
		"past_due": SubscriptionStatus.PAST_DUE,
		"canceled": SubscriptionStatus.CANCELED,
		"paused": SubscriptionStatus.PAUSED,
	}
	return mapping.get(stripe_status, SubscriptionStatus.ACTIVE)
