"""
Billing router for subscription management, usage tracking, and Stripe webhooks.

Provides endpoints for:
- GET  /billing/subscription  — current subscription + usage summary
- POST /billing/checkout      — create Stripe checkout session
- PATCH /billing/subscription — change tier or cancel subscription
- GET  /billing/usage         — detailed usage breakdown
- POST /billing/webhooks/stripe — Stripe webhook handler (public)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing_pricing import get_tier_features
from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.billing import (
	CheckoutRequest,
	CheckoutResponse,
	FeaturesResponse,
	OverageSummaryResponse,
	SubscriptionResponse,
	SubscriptionSummaryResponse,
	SubscriptionUpdateRequest,
	UsageBreakdownResponse,
	UsageMetricResponse,
	UsageResponse,
	StorageMetricResponse,
	OverageChargeResponse,
	PeriodResponse,
)
from ..services.billing_service import (
	cancel_subscription,
	create_checkout_session,
	get_or_create_subscription,
	process_stripe_webhook,
	update_subscription_tier,
)
from ..services.usage_service import get_usage_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=SubscriptionSummaryResponse)
async def get_subscription(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get current subscription status, usage, and features.

	Returns the user's subscription tier, billing status, usage metrics for
	the current period, and available features.

	Args:
		current_user: Authenticated user
		db: Database session

	Returns:
		SubscriptionSummaryResponse with subscription, usage, features, overage
	"""
	subscription = await get_or_create_subscription(db, current_user.id, current_user.tenant_id)
	usage_data = await get_usage_summary(db, current_user.id, current_user.tenant_id)

	features_dict = get_tier_features(subscription.tier)

	tts_providers = features_dict.get("tts_providers", ["google"])
	dist_targets = features_dict.get("distribution_targets", 1)
	team_members = features_dict.get("team_members", 1)
	concurrent = features_dict.get("concurrent_generations", 1)

	features = FeaturesResponse(
		tts_providers=tts_providers if isinstance(tts_providers, list) else "all",
		distribution_targets=dist_targets,
		team_members=team_members,
		concurrent_generations=concurrent,
	)

	price_monthly = subscription.price_monthly
	overage = OverageSummaryResponse(
		charges=usage_data["overage_charges"]["total"],
		estimated_next_bill=(
			float(price_monthly) + usage_data["overage_charges"]["total"]
			if price_monthly is not None
			else None
		),
	)

	usage_resp = _build_usage_breakdown(usage_data["usage"])

	return SubscriptionSummaryResponse(
		subscription=SubscriptionResponse.model_validate(subscription),
		usage=usage_resp,
		features=features,
		overage=overage,
	)


@router.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_200_OK)
async def create_checkout(
	checkout_request: CheckoutRequest,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create a Stripe Checkout session for upgrading to a paid tier.

	Args:
		checkout_request: Target tier and return URL
		current_user: Authenticated user
		db: Database session

	Returns:
		CheckoutResponse with the checkout URL

	Raises:
		HTTPException: 400 if tier is invalid or already subscribed
	"""
	result = await create_checkout_session(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		tier=checkout_request.tier,
		return_url=checkout_request.return_url,
	)
	await db.commit()
	return CheckoutResponse(**result)


@router.patch("/subscription", response_model=SubscriptionResponse)
async def update_subscription(
	update_request: SubscriptionUpdateRequest,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Change subscription tier or cancel subscription.

	Supported actions:
	- upgrade: Move to a higher tier (requires tier field)
	- downgrade: Move to a lower tier (requires tier field)
	- cancel: Cancel subscription (uses at_period_end flag)

	Args:
		update_request: Action and optional tier/flags
		current_user: Authenticated user
		db: Database session

	Returns:
		Updated SubscriptionResponse

	Raises:
		HTTPException: 400 if action or tier is invalid
	"""
	if update_request.action in ("upgrade", "downgrade"):
		if not update_request.tier:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="tier is required for upgrade/downgrade actions.",
			)
		subscription = await update_subscription_tier(
			db=db,
			user_id=current_user.id,
			tenant_id=current_user.tenant_id,
			new_tier=update_request.tier,
		)
	elif update_request.action == "cancel":
		subscription = await cancel_subscription(
			db=db,
			user_id=current_user.id,
			tenant_id=current_user.tenant_id,
			at_period_end=update_request.at_period_end,
		)
	else:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid action '{update_request.action}'. Must be upgrade, downgrade, or cancel.",
		)

	await db.commit()
	return SubscriptionResponse.model_validate(subscription)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get detailed usage breakdown for the current billing period.

	Returns episode count, storage, and API call usage relative to tier limits.

	Args:
		current_user: Authenticated user
		db: Database session

	Returns:
		UsageResponse with period dates, usage metrics, and overage charges
	"""
	usage_data = await get_usage_summary(db, current_user.id, current_user.tenant_id)

	return UsageResponse(
		period=PeriodResponse(**usage_data["period"]),
		usage=_build_usage_breakdown(usage_data["usage"]),
		overage_charges=OverageChargeResponse(**usage_data["overage_charges"]),
	)


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
	request: Request,
	db: AsyncSession = Depends(get_db),
	stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
	"""
	Handle incoming Stripe webhook events.

	Validates the Stripe signature (when STRIPE_WEBHOOK_SECRET is configured)
	and processes events like subscription updates, payment success/failure.

	This endpoint is public (no auth required) as it is called by Stripe.

	Args:
		request: Raw HTTP request (for signature verification)
		db: Database session
		stripe_signature: Stripe-Signature header

	Returns:
		{"received": True} on success

	Raises:
		HTTPException: 400 on signature verification failure
	"""
	body = await request.body()

	# Attempt Stripe signature verification if configured
	try:
		from ..config import settings
		import stripe

		webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
		if webhook_secret and stripe_signature:
			stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
			event = stripe.Webhook.construct_event(body, stripe_signature, webhook_secret)
			event_type = event["type"]
			event_data = event["data"]
		else:
			# No secret configured — parse JSON body directly (dev/test mode)
			import json
			payload = json.loads(body)
			event_type = payload.get("type", "")
			event_data = payload.get("data", {})
	except Exception as exc:
		logger.warning("Stripe webhook validation error: %s", exc)
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid webhook payload or signature.",
		)

	await process_stripe_webhook(db, event_type, event_data)
	await db.commit()
	return {"received": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_usage_breakdown(usage: dict) -> UsageBreakdownResponse:
	"""Convert raw usage dict to UsageBreakdownResponse."""
	ep = usage["episodes"]
	st = usage["storage"]
	api = usage["api_calls"]

	return UsageBreakdownResponse(
		episodes=UsageMetricResponse(
			count=ep["count"],
			limit=ep["limit"],
			percent=ep["percent"],
		),
		storage=StorageMetricResponse(
			bytes=st["bytes"],
			limit_bytes=st["limit_bytes"],
			gb=st["gb"],
			limit_gb=st["limit_gb"],
			percent=st["percent"],
		),
		api_calls=UsageMetricResponse(
			count=api["count"],
			limit=api["limit"],
			percent=api["percent"],
		),
	)
