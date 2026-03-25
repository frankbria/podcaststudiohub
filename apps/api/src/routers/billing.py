"""
Billing router: subscription management, usage tracking, and Stripe webhooks.
"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..utils.pricing import get_tier_features, get_tier_limit
from ..schemas.billing import (
	BillingOverviewResponse,
	CheckoutRequest,
	CheckoutResponse,
	OverageCharges,
	SubscriptionResponse,
	SubscriptionUpdateRequest,
	UsageDetailResponse,
	UsagePeriod,
)
from ..services import billing_service, usage_service

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# GET /billing/subscription — overview
# ---------------------------------------------------------------------------


@router.get("/subscription", response_model=BillingOverviewResponse)
async def get_subscription(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get current subscription, usage, and feature information."""
	sub = await billing_service.get_or_create_subscription(db, current_user.id, current_user.tenant_id)
	usage_data = await usage_service.get_usage_summary(db, current_user.id, current_user.tenant_id)
	tier_features = get_tier_features(sub.tier)

	# Overage
	period_start, _ = usage_service._current_period_dates()
	overage_cost = await usage_service.calculate_overage_cost(
		db, current_user.id, period_start, period_start  # period_end unused in calculation
	)
	tier_price = sub.price_monthly or Decimal("0")
	estimated_bill = tier_price + overage_cost

	return BillingOverviewResponse(
		subscription=SubscriptionResponse.model_validate(sub),
		usage=usage_data,
		features=tier_features,
		overage={
			"charges": overage_cost,
			"estimated_next_bill": estimated_bill,
		},
	)


# ---------------------------------------------------------------------------
# POST /billing/checkout — create Stripe checkout session
# ---------------------------------------------------------------------------


@router.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def create_checkout(
	checkout_req: CheckoutRequest,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Create a Stripe Checkout session for the selected tier."""
	result = await billing_service.create_checkout_session(
		db,
		current_user.id,
		current_user.tenant_id,
		checkout_req.tier,
		checkout_req.return_url,
	)
	return CheckoutResponse(**result)


# ---------------------------------------------------------------------------
# PATCH /billing/subscription — upgrade/downgrade/cancel
# ---------------------------------------------------------------------------


@router.patch("/subscription", response_model=SubscriptionResponse)
async def update_subscription(
	update_req: SubscriptionUpdateRequest,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Upgrade, downgrade, or cancel subscription."""
	if update_req.action == "cancel":
		sub = await billing_service.cancel_subscription(
			db, current_user.id, current_user.tenant_id, update_req.at_period_end
		)
	elif update_req.action in ("upgrade", "downgrade"):
		if not update_req.tier:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="tier is required for upgrade/downgrade actions",
			)
		sub = await billing_service.update_subscription_tier(
			db, current_user.id, current_user.tenant_id, update_req.tier
		)
	else:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Unknown action: {update_req.action}",
		)
	return SubscriptionResponse.model_validate(sub)


# ---------------------------------------------------------------------------
# GET /billing/usage — detailed usage breakdown
# ---------------------------------------------------------------------------


@router.get("/usage", response_model=UsageDetailResponse)
async def get_usage(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""Get detailed usage breakdown for the current billing period."""
	sub = await billing_service.get_or_create_subscription(db, current_user.id, current_user.tenant_id)
	tier = sub.tier
	usage_data = await usage_service.get_usage_summary(db, current_user.id, current_user.tenant_id)
	period_start, period_end = usage_service._current_period_dates()

	def _pct(count: int, limit: Optional[int]) -> Optional[float]:
		if limit is None or limit == 0:
			return None
		return round(count / limit * 100, 1)

	storage_gb = usage_data["storage_bytes"] / (1024 ** 3)
	storage_limit_gb = get_tier_limit(tier, "storage_gb")

	episodes = {
		"count": usage_data["episodes_created"],
		"limit": usage_data["episodes_limit"],
		"percent": _pct(usage_data["episodes_created"], usage_data["episodes_limit"]),
	}
	storage = {
		"bytes": usage_data["storage_bytes"],
		"limit_bytes": usage_data["storage_limit_bytes"],
		"gb": round(storage_gb, 4),
		"limit_gb": storage_limit_gb,
		"percent": _pct(usage_data["storage_bytes"], usage_data["storage_limit_bytes"]),
	}
	api_calls = {
		"count": usage_data["api_calls"],
		"limit": usage_data["api_calls_limit"],
		"percent": _pct(usage_data["api_calls"], usage_data["api_calls_limit"]),
	}

	overage_total = await usage_service.calculate_overage_cost(db, current_user.id, period_start, period_end)

	return UsageDetailResponse(
		period=UsagePeriod(start=period_start, end=period_end),
		usage={"episodes": episodes, "storage": storage, "api_calls": api_calls},
		overage_charges=OverageCharges(total=overage_total, line_items=[]),
	)


# ---------------------------------------------------------------------------
# POST /billing/webhooks/stripe — Stripe webhook handler (public)
# ---------------------------------------------------------------------------


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
	request: Request,
	db: AsyncSession = Depends(get_db),
):
	"""Handle Stripe webhook events."""
	payload = await request.body()
	sig_header = request.headers.get("stripe-signature")

	try:
		from ..config import settings  # type: ignore[import]
		webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
	except Exception:
		webhook_secret = None

	result = await billing_service.process_webhook(db, payload, sig_header, webhook_secret)
	return result
