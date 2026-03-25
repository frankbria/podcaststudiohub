"""Add billing subscription and usage tables

Revision ID: 010
Revises: 009
Create Date: 2026-03-25 00:00:00.000000

Creates two tables to support billing and subscription management:
  - billing_subscriptions: user subscription records
  - billing_usage: monthly resource usage tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# --- billing_subscriptions table ---
	op.create_table(
		"billing_subscriptions",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("tier", sa.String(50), nullable=False, server_default="free"),
		sa.Column("stripe_customer_id", sa.String(255), nullable=True),
		sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
		sa.Column("stripe_payment_method_id", sa.String(255), nullable=True),
		sa.Column("billing_cycle_start", sa.DateTime(), nullable=True),
		sa.Column("billing_cycle_end", sa.DateTime(), nullable=True),
		sa.Column("renewal_date", sa.DateTime(), nullable=True),
		sa.Column("status", sa.String(50), nullable=False, server_default="active"),
		sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default="true"),
		sa.Column("price_monthly", sa.Numeric(10, 2), nullable=True),
		sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
		sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("canceled_at", sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
		sa.UniqueConstraint("user_id", name="uq_billing_subscriptions_user_id"),
		sa.UniqueConstraint("stripe_customer_id", name="uq_billing_subscriptions_stripe_customer_id"),
		sa.UniqueConstraint("stripe_subscription_id", name="uq_billing_subscriptions_stripe_subscription_id"),
	)
	op.create_index("ix_billing_subscriptions_user_id", "billing_subscriptions", ["user_id"])
	op.create_index("ix_billing_subscriptions_tenant_id", "billing_subscriptions", ["tenant_id"])

	# --- billing_usage table ---
	op.create_table(
		"billing_usage",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("period_start", sa.Date(), nullable=False),
		sa.Column("period_end", sa.Date(), nullable=False),
		sa.Column("episodes_created", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("api_calls", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("storage_bytes", sa.BigInteger(), nullable=False, server_default="0"),
		sa.Column("compute_hours", sa.Float(), nullable=False, server_default="0"),
		sa.Column("overage_episodes", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("overage_storage_gb", sa.Float(), nullable=False, server_default="0"),
		sa.Column("overage_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
		sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
	)
	op.create_index("ix_billing_usage_user_id", "billing_usage", ["user_id"])

	# Grant permissions to app role
	op.execute("GRANT ALL ON billing_subscriptions TO podcastfy_app")
	op.execute("GRANT ALL ON billing_usage TO podcastfy_app")


def downgrade() -> None:
	op.drop_table("billing_usage")
	op.drop_table("billing_subscriptions")
