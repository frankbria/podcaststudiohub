"""Billing usage model for tracking resource consumption"""

from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, Float, DateTime, Date, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..database import Base


class BillingUsage(Base):
	"""Track usage for pricing enforcement and overage charges"""

	__tablename__ = "billing_usage"
	__table_args__ = (
		UniqueConstraint("user_id", "period_start", name="uq_billing_usage_user_period"),
	)

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
	tenant_id = Column(UUID(as_uuid=True), nullable=False)

	# Billing period
	period_start = Column(Date, nullable=False)
	period_end = Column(Date, nullable=False)

	# Usage metrics
	episodes_created = Column(Integer, default=0, nullable=False)
	api_calls = Column(Integer, default=0, nullable=False)
	storage_bytes = Column(BigInteger, default=0, nullable=False)
	compute_hours = Column(Float, default=0, nullable=False)

	# Overage charges
	overage_episodes = Column(Integer, default=0, nullable=False)
	overage_storage_gb = Column(Float, default=0, nullable=False)
	overage_cost = Column(Numeric(10, 2), default=0, nullable=False)

	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

	def __repr__(self) -> str:
		return f"<BillingUsage(user_id={self.user_id}, period={self.period_start})>"
