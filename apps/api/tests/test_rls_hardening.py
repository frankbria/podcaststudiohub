"""RLS defense-in-depth hardening (issue #304).

Verifies the DB-layer backstops added by migration 014:
- billing_subscriptions / billing_usage / analytics_events are FORCE-RLS'd with
  tenant_isolation policies (cross-tenant reads return nothing, mismatched-tenant
  writes are rejected).
- The permissive ``tenant_isolation_insert_*`` WITH CHECK (true) policies are gone:
  INSERTs whose tenant_id doesn't match app.tenant_id are rejected on core tables.
- The blanket ``users_auth_lookup`` USING (true) SELECT policy is gone; auth
  bootstraps through narrow SECURITY DEFINER lookup functions instead.
- The Stripe webhook (no JWT -> no tenant context) still updates subscriptions by
  bootstrapping tenant context from the stripe_customer_id definer lookup.

All tests run on the non-superuser podcastfy_app role (see conftest) so FORCE RLS
is actually exercised.
"""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from src.database import set_tenant_context
from src.models.billing_subscription import BillingSubscription
from src.models.billing_usage import BillingUsage
from src.models.analytics_event import AnalyticsEvent
from src.models.user import User
from src.services.auth_service import authenticate_user, create_user, get_user_by_email
from src.services.billing_service import (
    _handle_subscription_deleted,
    _handle_subscription_updated,
)


async def _make_user(test_db, email: str) -> User:
    """Create a user through the real registration path (arms its own context)."""
    return await create_user(
        session=test_db, email=email, password="Str0ng!pass", full_name="RLS Test"
    )


# ---------------------------------------------------------------------------
# Billing / analytics tables: FORCE RLS + tenant_isolation policies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_billing_subscription_hidden_from_other_tenant(test_db):
    user = await _make_user(test_db, f"rls-billing-{uuid4().hex[:8]}@example.com")

    await set_tenant_context(test_db, str(user.tenant_id))
    sub = BillingSubscription(
        id=uuid4(),
        user_id=user.id,
        tenant_id=user.tenant_id,
        tier="pro",
        stripe_customer_id=f"cus_{uuid4().hex[:12]}",
    )
    test_db.add(sub)
    await test_db.flush()

    # Same tenant sees it
    result = await test_db.execute(
        select(BillingSubscription).where(BillingSubscription.user_id == user.id)
    )
    assert result.scalar_one_or_none() is not None

    # Another tenant's context sees nothing, even without a WHERE tenant filter
    await set_tenant_context(test_db, str(uuid4()))
    result = await test_db.execute(
        select(BillingSubscription).where(BillingSubscription.user_id == user.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_billing_usage_hidden_from_other_tenant(test_db):
    user = await _make_user(test_db, f"rls-usage-{uuid4().hex[:8]}@example.com")

    await set_tenant_context(test_db, str(user.tenant_id))
    usage = BillingUsage(
        id=uuid4(),
        user_id=user.id,
        tenant_id=user.tenant_id,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
    )
    test_db.add(usage)
    await test_db.flush()

    await set_tenant_context(test_db, str(uuid4()))
    result = await test_db.execute(
        select(BillingUsage).where(BillingUsage.user_id == user.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_analytics_events_hidden_from_other_tenant(test_db):
    user = await _make_user(test_db, f"rls-analytics-{uuid4().hex[:8]}@example.com")

    await set_tenant_context(test_db, str(user.tenant_id))
    event = AnalyticsEvent(
        id=uuid4(),
        tenant_id=user.tenant_id,
        event_type="download",
    )
    test_db.add(event)
    await test_db.flush()

    await set_tenant_context(test_db, str(uuid4()))
    result = await test_db.execute(
        select(AnalyticsEvent).where(AnalyticsEvent.id == event.id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_analytics_insert_with_mismatched_tenant_rejected(test_db):
    """WITH CHECK on the new analytics policy rejects a spoofed tenant_id."""
    user = await _make_user(test_db, f"rls-spoof-{uuid4().hex[:8]}@example.com")
    await set_tenant_context(test_db, str(user.tenant_id))

    event = AnalyticsEvent(id=uuid4(), tenant_id=uuid4(), event_type="download")
    test_db.add(event)
    with pytest.raises(DBAPIError, match="row-level security"):
        await test_db.flush()
    await test_db.rollback()


# ---------------------------------------------------------------------------
# Core tables: permissive INSERT WITH CHECK (true) policies removed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_core_table_insert_with_mismatched_tenant_rejected(test_db):
    """Inserting a project whose tenant_id != app.tenant_id must fail (backstop
    against tenant-id-from-input bugs). Previously allowed by
    tenant_isolation_insert_projects WITH CHECK (true)."""
    user = await _make_user(test_db, f"rls-proj-{uuid4().hex[:8]}@example.com")
    await set_tenant_context(test_db, str(user.tenant_id))

    with pytest.raises(DBAPIError, match="row-level security"):
        await test_db.execute(
            text(
                "INSERT INTO projects (id, tenant_id, user_id, name, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :user_id, 'spoof', now(), now())"
            ),
            {"id": uuid4(), "tenant_id": uuid4(), "user_id": user.id},
        )
    await test_db.rollback()


@pytest.mark.asyncio
async def test_registration_insert_still_works_without_prior_context(test_db):
    """create_user is the one pre-tenant INSERT: it must arm the new tenant's
    context itself so the scoped WITH CHECK passes."""
    email = f"rls-register-{uuid4().hex[:8]}@example.com"
    user = await _make_user(test_db, email)
    assert user.id is not None
    assert user.tenant_id is not None


# ---------------------------------------------------------------------------
# users table: blanket USING (true) SELECT replaced by SECURITY DEFINER lookup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_users_direct_select_blocked_across_tenants(test_db):
    """A plain SELECT on users under another tenant's context must return
    nothing — the users_auth_lookup USING (true) policy is gone."""
    email = f"rls-users-{uuid4().hex[:8]}@example.com"
    user = await _make_user(test_db, email)

    await set_tenant_context(test_db, str(uuid4()))
    result = await test_db.execute(select(User).where(User.id == user.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_auth_lookup_by_email_works_across_contexts(test_db):
    """get_user_by_email must keep working with no/foreign tenant context via
    the SECURITY DEFINER lookup (login + resend-verification bootstrap)."""
    email = f"rls-lookup-{uuid4().hex[:8]}@example.com"
    created = await _make_user(test_db, email)

    # Foreign tenant context — the definer function must still find the user
    await set_tenant_context(test_db, str(uuid4()))
    found = await get_user_by_email(test_db, email.upper())  # case-insensitive
    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio
async def test_authenticate_user_works_without_tenant_context(test_db):
    """Login: authenticate_user must find the user pre-tenant and still update
    last_login under the user's own context."""
    email = f"rls-login-{uuid4().hex[:8]}@example.com"
    await _make_user(test_db, email)

    await set_tenant_context(test_db, str(uuid4()))
    user = await authenticate_user(test_db, email, "Str0ng!pass")
    assert user is not None
    assert user.last_login is not None


# ---------------------------------------------------------------------------
# Stripe webhook: bootstraps tenant context from stripe_customer_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_subscription_updated_without_tenant_context(test_db):
    user = await _make_user(test_db, f"rls-hook-{uuid4().hex[:8]}@example.com")
    customer_id = f"cus_{uuid4().hex[:12]}"

    await set_tenant_context(test_db, str(user.tenant_id))
    sub = BillingSubscription(
        id=uuid4(),
        user_id=user.id,
        tenant_id=user.tenant_id,
        tier="pro",
        status="active",
        stripe_customer_id=customer_id,
    )
    test_db.add(sub)
    await test_db.flush()

    # Simulate the webhook's session state: some unrelated (effectively no)
    # tenant context — the handler must bootstrap the right tenant itself.
    await set_tenant_context(test_db, str(uuid4()))
    await _handle_subscription_updated(
        test_db,
        {"id": f"sub_{uuid4().hex[:12]}", "customer": customer_id, "status": "past_due"},
    )

    await set_tenant_context(test_db, str(user.tenant_id))
    result = await test_db.execute(
        select(BillingSubscription).where(
            BillingSubscription.stripe_customer_id == customer_id
        )
    )
    refreshed = result.scalar_one()
    assert refreshed.status == "past_due"


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_without_tenant_context(test_db):
    user = await _make_user(test_db, f"rls-hookdel-{uuid4().hex[:8]}@example.com")
    customer_id = f"cus_{uuid4().hex[:12]}"

    await set_tenant_context(test_db, str(user.tenant_id))
    sub = BillingSubscription(
        id=uuid4(),
        user_id=user.id,
        tenant_id=user.tenant_id,
        tier="pro",
        status="active",
        stripe_customer_id=customer_id,
    )
    test_db.add(sub)
    await test_db.flush()

    await set_tenant_context(test_db, str(uuid4()))
    await _handle_subscription_deleted(test_db, {"customer": customer_id})

    await set_tenant_context(test_db, str(user.tenant_id))
    result = await test_db.execute(
        select(BillingSubscription).where(
            BillingSubscription.stripe_customer_id == customer_id
        )
    )
    refreshed = result.scalar_one()
    assert refreshed.status == "canceled"
    assert refreshed.canceled_at is not None


@pytest.mark.asyncio
async def test_webhook_unknown_customer_is_noop(test_db):
    await set_tenant_context(test_db, str(uuid4()))
    # Must not raise for a customer id that matches no subscription
    await _handle_subscription_updated(
        test_db, {"id": "sub_x", "customer": "cus_does_not_exist", "status": "active"}
    )
