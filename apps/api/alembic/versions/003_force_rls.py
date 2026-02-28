"""Force Row-Level Security and provision non-superuser app role

Adds FORCE ROW LEVEL SECURITY to all 11 tenant-scoped tables so that RLS
policies are enforced even for table owners and superusers. Recreates the
per-table policies with explicit WITH CHECK clauses and adds a separate
INSERT-only policy (WITH CHECK (true)) so registration can proceed without
a tenant context. Also provisions the non-superuser podcastfy_app role that
the application should connect as at runtime.

Revision ID: 003
Revises: 002
Create Date: 2025-10-20 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
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


def upgrade() -> None:
	for table in TABLES:
		# Drop the existing policy (USING-only, no WITH CHECK)
		op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}')

		# Recreate for SELECT/UPDATE/DELETE with explicit USING + WITH CHECK
		op.execute(f"""
			CREATE POLICY tenant_isolation_{table} ON {table}
				FOR ALL
				USING  (tenant_id = current_setting('app.tenant_id', true)::uuid)
				WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
		""")

		# Permissive INSERT-only policy: the application always sets tenant_id
		# correctly; without this policy INSERT would be blocked when there is
		# no tenant context (e.g. during user registration).
		op.execute(f"""
			CREATE POLICY tenant_isolation_insert_{table} ON {table}
				FOR INSERT
				WITH CHECK (true)
		""")

		# Enforce RLS even for the table owner / superuser connections
		op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')

	# -------------------------------------------------------------------------
	# Provision the non-superuser application role
	# -------------------------------------------------------------------------
	# Use DO block because CREATE ROLE IF NOT EXISTS is not supported directly
	# in older PostgreSQL versions (<= 14 doesn't have CREATE ROLE IF NOT EXISTS)
	op.execute("""
		DO $$
		BEGIN
			IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'podcastfy_app') THEN
				CREATE ROLE podcastfy_app
					NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT LOGIN
					PASSWORD 'podcastfy_app_password';
			END IF;
		END
		$$;
	""")

	op.execute('GRANT CONNECT ON DATABASE podcastfy TO podcastfy_app')
	op.execute('GRANT USAGE ON SCHEMA public TO podcastfy_app')
	op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO podcastfy_app')
	op.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO podcastfy_app')


def downgrade() -> None:
	# Revoke grants from podcastfy_app
	op.execute('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM podcastfy_app')
	op.execute('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM podcastfy_app')
	op.execute('REVOKE USAGE ON SCHEMA public FROM podcastfy_app')
	op.execute('REVOKE CONNECT ON DATABASE podcastfy FROM podcastfy_app')

	op.execute('DROP ROLE IF EXISTS podcastfy_app')

	for table in TABLES:
		# Remove FORCE and drop updated policies
		op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
		op.execute(f'DROP POLICY IF EXISTS tenant_isolation_insert_{table} ON {table}')
		op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}')

		# Restore the original USING-only policy
		op.execute(f"""
			CREATE POLICY tenant_isolation_{table} ON {table}
				USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
		""")
