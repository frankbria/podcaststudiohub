"""RLS defense-in-depth hardening (issue #304)

- Adds ENABLE + FORCE ROW LEVEL SECURITY and tenant_isolation policies to the
  billing_subscriptions, billing_usage and analytics_events tables (created in
  010/011 with tenant_id columns but no RLS).
- Drops the permissive tenant_isolation_insert_* WITH CHECK (true) policies:
  policies OR together, so they nullified the FOR ALL policy's WITH CHECK on
  INSERT. With them gone, INSERTs must satisfy
  tenant_id = current_setting('app.tenant_id')::uuid. Registration (the one
  pre-tenant INSERT) now arms the new tenant's context itself (auth_service).
- Drops the blanket users_auth_lookup FOR SELECT USING (true) policy, which
  exposed every user row (password_hash, encrypted_api_keys) across tenants.
  Auth bootstraps through a narrow SECURITY DEFINER lookup instead; the Stripe
  webhook gets an equivalent stripe_customer_id -> tenant_id lookup.
- Rotates the podcastfy_app role password when APP_DB_PASSWORD is set (no-op
  otherwise, so CI and local dev keep their locally provisioned passwords).

Revision ID: 014
Revises: 013
Create Date: 2026-07-09 12:00:00.000000

"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The 11 core tenant-scoped tables from migration 003
CORE_TABLES = [
    'users',
    'conversation_templates',
    'tts_configurations',
    'projects',
    'episodes',
    'content_sources',
    'rss_feeds',
    'distribution_targets',
    'audio_snippets',
    'episode_layouts',
    'episode_compositions',
]

# Tenant-scoped tables added after 003 without RLS
BILLING_ANALYTICS_TABLES = [
    'billing_subscriptions',
    'billing_usage',
    'analytics_events',
]

LOOKUP_FUNCTIONS = [
    'auth_lookup_user_by_email(text)',
    'billing_tenant_for_stripe_customer(text)',
]


def upgrade() -> None:
    # 0. The SECURITY DEFINER functions below must be owned by a role that can
    #    read through FORCE RLS, or auth breaks for every user. Fail loudly if
    #    Alembic fell back to the RLS-subject app role (MIGRATION_DATABASE_URL
    #    unset — issue #301).
    op.execute("""
        DO $do$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles
                WHERE rolname = current_user AND (rolsuper OR rolbypassrls)
            ) THEN
                RAISE EXCEPTION
                    'migration 014 must run as a superuser/BYPASSRLS role '
                    '(set MIGRATION_DATABASE_URL); running as % would leave '
                    'auth lookup functions unable to read through FORCE RLS',
                    current_user;
            END IF;
        END
        $do$;
    """)

    # 1. Billing/analytics tables: same FORCE-RLS + tenant policy as the core
    #    tables get in 003.
    for table in BILLING_ANALYTICS_TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
                FOR ALL
                USING  (tenant_id = current_setting('app.tenant_id', true)::uuid)
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """)
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')

    # 2. Drop the permissive INSERT policies. The FOR ALL tenant_isolation
    #    policy's WITH CHECK then governs INSERT on every core table.
    for table in CORE_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_insert_{table} ON {table}')

    # 3. Replace the blanket users SELECT policy with narrow SECURITY DEFINER
    #    lookups. Owner is the migration role (BYPASSRLS), so the function can
    #    read through FORCE RLS; EXECUTE is granted only to the app role.
    op.execute('DROP POLICY IF EXISTS users_auth_lookup ON users')

    # Least-privilege by construction: the function discloses ONLY
    # (id, tenant_id) for a given email — never password_hash or
    # encrypted_api_keys. Callers set that tenant's context and load the full
    # row through the normal RLS-governed SELECT.
    op.execute("""
        CREATE OR REPLACE FUNCTION auth_lookup_user_by_email(p_email text)
        RETURNS TABLE (id uuid, tenant_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $fn$
            SELECT id, tenant_id FROM users WHERE lower(email) = lower(p_email)
        $fn$
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION billing_tenant_for_stripe_customer(p_customer_id text)
        RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $fn$
            SELECT tenant_id FROM billing_subscriptions
            WHERE stripe_customer_id = p_customer_id
        $fn$
    """)

    for fn in LOOKUP_FUNCTIONS:
        op.execute(f'REVOKE ALL ON FUNCTION {fn} FROM PUBLIC')
        op.execute(f'GRANT EXECUTE ON FUNCTION {fn} TO podcastfy_app')

    # 4. Rotate the app role password when a secret is provided (deploys set
    #    APP_DB_PASSWORD; CI/local keep their locally provisioned passwords).
    #    The secret travels as a bound parameter into a transaction-local GUC,
    #    then through format(%L) — never interpolated into SQL text.
    app_db_password = os.environ.get('APP_DB_PASSWORD')
    if app_db_password:
        op.get_bind().execute(
            sa.text("SELECT set_config('app.bootstrap_pw', :pw, true)"),
            {"pw": app_db_password},
        )
        op.execute("""
            DO $do$
            BEGIN
                EXECUTE format(
                    'ALTER ROLE podcastfy_app PASSWORD %L',
                    current_setting('app.bootstrap_pw')
                );
            END
            $do$;
        """)


def downgrade() -> None:
    for fn in LOOKUP_FUNCTIONS:
        op.execute(f'DROP FUNCTION IF EXISTS {fn}')

    op.execute("""
        CREATE POLICY users_auth_lookup ON users
            FOR SELECT
            USING (true)
    """)

    for table in CORE_TABLES:
        op.execute(f"""
            CREATE POLICY tenant_isolation_insert_{table} ON {table}
                FOR INSERT
                WITH CHECK (true)
        """)

    for table in BILLING_ANALYTICS_TABLES:
        op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')

    # Password rotation is intentionally not reverted.
