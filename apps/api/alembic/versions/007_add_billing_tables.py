"""Add billing_subscriptions and billing_usage tables

Revision ID: 007
Revises: 006
Create Date: 2026-03-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table: billing_subscriptions
    op.create_table(
        'billing_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tier', sa.Text(), nullable=False, server_default='free'),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True, unique=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True, unique=True),
        sa.Column('stripe_payment_method_id', sa.String(255), nullable=True),
        sa.Column('billing_cycle_start', sa.DateTime(), nullable=True),
        sa.Column('billing_cycle_end', sa.DateTime(), nullable=True),
        sa.Column('renewal_date', sa.DateTime(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('price_monthly', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('canceled_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_billing_subscriptions_user_id', 'billing_subscriptions', ['user_id'])
    op.create_index('idx_billing_subscriptions_tenant_id', 'billing_subscriptions', ['tenant_id'])

    # Trigger to auto-update updated_at
    op.execute("""
        CREATE TRIGGER billing_subscriptions_updated_at
        BEFORE UPDATE ON billing_subscriptions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # RLS for billing_subscriptions
    op.execute("ALTER TABLE billing_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing_subscriptions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY billing_subscriptions_tenant_isolation
        ON billing_subscriptions
        USING (tenant_id::text = current_setting('app.tenant_id', true))
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON billing_subscriptions TO podcastfy_app")

    # Table: billing_usage
    op.create_table(
        'billing_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('episodes_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('api_calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('storage_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('compute_hours', sa.Float(), nullable=False, server_default='0'),
        sa.Column('overage_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('overage_storage_gb', sa.Float(), nullable=False, server_default='0'),
        sa.Column('overage_cost', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_billing_usage_user_id', 'billing_usage', ['user_id'])
    op.create_index('idx_billing_usage_user_period', 'billing_usage', ['user_id', 'period_start'])

    # Trigger to auto-update updated_at
    op.execute("""
        CREATE TRIGGER billing_usage_updated_at
        BEFORE UPDATE ON billing_usage
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # RLS for billing_usage
    op.execute("ALTER TABLE billing_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE billing_usage FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY billing_usage_tenant_isolation
        ON billing_usage
        USING (tenant_id::text = current_setting('app.tenant_id', true))
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON billing_usage TO podcastfy_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS billing_usage CASCADE")
    op.execute("DROP TABLE IF EXISTS billing_subscriptions CASCADE")
