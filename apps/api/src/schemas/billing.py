"""Pydantic schemas for billing and subscription endpoints"""

from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Subscription schemas
# ---------------------------------------------------------------------------


class SubscriptionResponse(BaseModel):
	"""Current subscription details"""

	tier: str
	status: str
	price_monthly: Optional[Decimal]
	currency: str
	billing_cycle_start: Optional[datetime]
	billing_cycle_end: Optional[datetime]
	renewal_date: Optional[datetime]
	auto_renew: bool
	stripe_customer_id: Optional[str]
	stripe_subscription_id: Optional[str]

	model_config = {"from_attributes": True}


class UsageSummary(BaseModel):
	"""Usage summary for the current billing period"""

	episodes_created: int
	episodes_limit: Optional[int]
	storage_bytes: int
	storage_limit_bytes: Optional[int]
	api_calls: int
	api_calls_limit: Optional[int]


class OverageInfo(BaseModel):
	"""Overage charge information"""

	charges: Decimal
	estimated_next_bill: Optional[Decimal]


class BillingOverviewResponse(BaseModel):
	"""Full billing overview: subscription + usage + features"""

	subscription: SubscriptionResponse
	usage: UsageSummary
	features: Dict[str, Any]
	overage: OverageInfo


# ---------------------------------------------------------------------------
# Checkout schemas
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
	"""Request to create a Stripe checkout session"""

	tier: str = Field(..., pattern="^(pro|enterprise)$")
	return_url: Optional[str] = None


class CheckoutResponse(BaseModel):
	"""Stripe checkout session response"""

	checkout_url: str


# ---------------------------------------------------------------------------
# Subscription update schemas
# ---------------------------------------------------------------------------


class SubscriptionUpdateRequest(BaseModel):
	"""Request to upgrade, downgrade, or cancel subscription"""

	action: str = Field(..., pattern="^(upgrade|downgrade|cancel)$")
	tier: Optional[str] = Field(None, pattern="^(free|pro|enterprise)$")
	at_period_end: bool = True


# ---------------------------------------------------------------------------
# Usage detail schemas
# ---------------------------------------------------------------------------


class UsageMetric(BaseModel):
	"""Single usage metric with limit and percentage"""

	count: int
	limit: Optional[int]
	percent: Optional[float]


class StorageMetric(BaseModel):
	"""Storage usage metric"""

	bytes: int
	limit_bytes: Optional[int]
	gb: float
	limit_gb: Optional[float]
	percent: Optional[float]


class OverageLineItem(BaseModel):
	"""A single overage charge line item"""

	description: str
	quantity: float
	unit_cost: Decimal
	total: Decimal


class OverageCharges(BaseModel):
	"""Overage charges breakdown"""

	total: Decimal
	line_items: List[OverageLineItem]


class UsagePeriod(BaseModel):
	"""Usage period start/end dates"""

	start: date
	end: date


class UsageDetailResponse(BaseModel):
	"""Detailed usage breakdown for a billing period"""

	period: UsagePeriod
	usage: Dict[str, Any]
	overage_charges: OverageCharges
