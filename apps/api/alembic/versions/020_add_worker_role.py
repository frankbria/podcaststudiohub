"""Add the podcastfy_worker role: Celery's DB identity, which bypasses RLS

Celery tasks run with no tenant context. Under the FORCE-RLS app role
(podcastfy_app) every read inside a task returned nothing: on the dev box the
worker connected as podcastfy_app, and 11 content extractions reported their
own existing rows "not found" (issue #649). The code assumed the worker
bypasses RLS, which held only while its URL was the superuser's.

podcastfy_worker is a login role with BYPASSRLS and nothing else:
- NOSUPERUSER, NOCREATEDB, NOCREATEROLE: it is not the superuser.
- INHERIT, member of podcastfy_app: it gets exactly the app role's table
  grants, including every future grant a migration gives podcastfy_app, so
  there is no second grant list to keep in sync. Role attributes such as
  BYPASSRLS are not inherited through membership, so podcastfy_app stays
  RLS-forced.

The worker uses it through CELERY_DATABASE_URL. Fresh installs take the
password from WORKER_DB_PASSWORD; the literal fallback keeps local dev and CI
working, as migration 003 does for the app role. The secret travels as a
bound parameter into a transaction-local GUC, then through format(%L), never
interpolated into SQL text. Idempotent: an existing role is left as it is.

Creating a BYPASSRLS role needs a superuser, which the migration URL is
(MIGRATION_DATABASE_URL, issue #301).

Revision ID: 020
Revises: 019
Create Date: 2026-10-13 00:00:00.000000

"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    worker_password = os.environ.get('WORKER_DB_PASSWORD', 'podcastfy_worker_password')
    op.get_bind().execute(
        sa.text("SELECT set_config('app.bootstrap_worker_pw', :pw, true)"),
        {"pw": worker_password},
    )
    op.execute("""
        DO $do$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'podcastfy_worker') THEN
                EXECUTE format(
                    'CREATE ROLE podcastfy_worker '
                    'NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT LOGIN BYPASSRLS '
                    'PASSWORD %L IN ROLE podcastfy_app',
                    current_setting('app.bootstrap_worker_pw')
                );
            END IF;
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO podcastfy_worker', current_database());
        END
        $do$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'podcastfy_worker') THEN
                EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM podcastfy_worker', current_database());
                DROP ROLE podcastfy_worker;
            END IF;
        END
        $do$;
    """)
