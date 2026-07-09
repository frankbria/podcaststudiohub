"""Billing subscription model for user subscription management"""

from enum import Enum
from sqlalchemy import Column, String, DateTime, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow


class SubscriptionTier(str, Enum):
	FREE = "free"
	PRO = "pro"
	ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
	ACTIVE = "active"
	PAUSED = "paused"
	CANCELED = "canceled"
	PAST_DUE = "past_due"


class BillingSubscription(Base):
	"""User subscription and billing information"""

	__tablename__ = "billing_subscriptions"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
	tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

	# Subscription tier
	tier = Column(String(50), nullable=False, default=SubscriptionTier.FREE)

	# Stripe integration
	stripe_customer_id = Column(String(255), unique=True, nullable=True)
	stripe_subscription_id = Column(String(255), unique=True, nullable=True)
	stripe_payment_method_id = Column(String(255), nullable=True)

	# Billing cycle
	billing_cycle_start = Column(DateTime, nullable=True)
	billing_cycle_end = Column(DateTime, nullable=True)
	renewal_date = Column(DateTime, nullable=True)

	# Status
	status = Column(String(50), default=SubscriptionStatus.ACTIVE, nullable=False)
	auto_renew = Column(Boolean, default=True, nullable=False)

	# Pricing
	price_monthly = Column(Numeric(10, 2), nullable=True)
	currency = Column(String(3), default="USD", nullable=False)

	# Timestamps
	created_at = Column(DateTime, default=utcnow, nullable=False)
	updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
	canceled_at = Column(DateTime, nullable=True)

	def __repr__(self) -> str:
		return f"<BillingSubscription(user_id={self.user_id}, tier={self.tier}, status={self.status})>"
