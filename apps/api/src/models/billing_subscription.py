"""Billing subscription model for user subscription tiers and Stripe integration"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base


class SubscriptionTier(str, Enum):
	FREE = "free"
	PRO = "pro"
	ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
	ACTIVE = "active"
	PAUSED = "paused"
	CANCELED = "canceled"
	PAST_DUE = "past_due"
	TRIALING = "trialing"


class BillingSubscription(Base):
	"""User subscription and billing information"""

	__tablename__ = "billing_subscriptions"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(
		UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		unique=True,
		nullable=False,
		index=True,
	)
	tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

	# Subscription tier
	tier = Column(Text, nullable=False, default=SubscriptionTier.FREE)

	# Stripe integration
	stripe_customer_id = Column(String(255), unique=True, nullable=True)
	stripe_subscription_id = Column(String(255), unique=True, nullable=True)
	stripe_payment_method_id = Column(String(255), nullable=True)

	# Billing cycle
	billing_cycle_start = Column(DateTime, nullable=True)
	billing_cycle_end = Column(DateTime, nullable=True)
	renewal_date = Column(DateTime, nullable=True)

	# Status
	status = Column(Text, nullable=False, default=SubscriptionStatus.ACTIVE)
	auto_renew = Column(Boolean, default=True, nullable=False)

	# Pricing
	price_monthly = Column(Numeric(10, 2), nullable=True)
	currency = Column(String(3), default="USD", nullable=False)

	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
	canceled_at = Column(DateTime, nullable=True)

	# Relationships
	user = relationship("User")

	def __repr__(self) -> str:
		return f"<BillingSubscription(id={self.id}, user_id={self.user_id}, tier={self.tier}, status={self.status})>"
