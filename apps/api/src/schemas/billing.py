"""Billing schemas for request/response validation"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Subscription schemas
# ---------------------------------------------------------------------------

class SubscriptionResponse(BaseModel):
	"""Current subscription details."""

	id: UUID
	user_id: UUID
	tenant_id: UUID
	tier: str
	status: str
	price_monthly: Optional[Decimal] = None
	currency: str
	billing_cycle_start: Optional[datetime] = None
	billing_cycle_end: Optional[datetime] = None
	renewal_date: Optional[datetime] = None
	auto_renew: bool
	stripe_customer_id: Optional[str] = None
	stripe_subscription_id: Optional[str] = None
	created_at: datetime
	updated_at: datetime
	canceled_at: Optional[datetime] = None

	model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
	"""Request body for creating a checkout session."""

	tier: str = Field(..., description="Target subscription tier (pro, enterprise)")
	return_url: str = Field(..., description="URL to redirect after checkout")


class CheckoutResponse(BaseModel):
	"""Response with Stripe checkout URL."""

	checkout_url: str


class SubscriptionUpdateRequest(BaseModel):
	"""Request body for changing subscription tier or canceling."""

	action: str = Field(
		...,
		description="Action to perform: upgrade, downgrade, or cancel",
	)
	tier: Optional[str] = Field(
		None,
		description="Target tier for upgrade/downgrade",
	)
	at_period_end: bool = Field(
		True,
		description="For cancel: whether to cancel at period end (True) or immediately (False)",
	)


# ---------------------------------------------------------------------------
# Usage schemas
# ---------------------------------------------------------------------------

class UsageMetricResponse(BaseModel):
	"""Usage metric with count, limit, and percent."""

	count: int
	limit: Optional[int] = None
	percent: Optional[int] = None


class StorageMetricResponse(BaseModel):
	"""Storage usage metric."""

	bytes: int
	limit_bytes: Optional[int] = None
	gb: float
	limit_gb: Optional[float] = None
	percent: Optional[int] = None


class UsageBreakdownResponse(BaseModel):
	"""Detailed usage breakdown."""

	episodes: UsageMetricResponse
	storage: StorageMetricResponse
	api_calls: UsageMetricResponse


class OverageChargeResponse(BaseModel):
	"""Overage charge information."""

	total: float
	line_items: List[Dict[str, Any]] = []


class PeriodResponse(BaseModel):
	"""Billing period dates."""

	start: str
	end: str


class UsageResponse(BaseModel):
	"""Full usage summary response."""

	period: PeriodResponse
	usage: UsageBreakdownResponse
	overage_charges: OverageChargeResponse


# ---------------------------------------------------------------------------
# Full subscription + usage summary
# ---------------------------------------------------------------------------

class FeaturesResponse(BaseModel):
	"""Feature access for a subscription tier."""

	tts_providers: Union[List[str], str]
	distribution_targets: Union[int, str]
	team_members: Union[int, str]
	concurrent_generations: Union[int, str]


class OverageSummaryResponse(BaseModel):
	"""Overage and next bill estimate."""

	charges: float
	estimated_next_bill: Optional[float] = None


class SubscriptionSummaryResponse(BaseModel):
	"""Combined subscription, usage, and features summary."""

	subscription: SubscriptionResponse
	usage: UsageBreakdownResponse
	features: FeaturesResponse
	overage: OverageSummaryResponse


# ---------------------------------------------------------------------------
# Webhook schema
# ---------------------------------------------------------------------------

class StripeWebhookRequest(BaseModel):
	"""Stripe webhook event payload."""

	type: str
	data: Dict[str, Any]
	id: Optional[str] = None
	livemode: Optional[bool] = None
