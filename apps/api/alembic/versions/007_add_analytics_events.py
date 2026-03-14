"""Add analytics_events table for usage tracking

Revision ID: 007
Revises: 006
Create Date: 2026-03-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'analytics_events',
		sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
		sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
		sa.Column('episode_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=True),
		sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True),
		sa.Column('event_type', sa.Text(), nullable=False),
		sa.Column('user_agent', sa.Text(), nullable=True),
		sa.Column('referer', sa.Text(), nullable=True),
		sa.Column('ip_hash', sa.Text(), nullable=True),
		sa.Column('country', sa.Text(), nullable=True),
		sa.Column('device_type', sa.Text(), nullable=True),
		sa.Column('app_name', sa.Text(), nullable=True),
		sa.Column('metadata', postgresql.JSONB(), nullable=True),
		sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
	)

	op.create_index('idx_analytics_events_tenant', 'analytics_events', ['tenant_id'])
	op.create_index('idx_analytics_events_episode', 'analytics_events', ['episode_id'])
	op.create_index('idx_analytics_events_project', 'analytics_events', ['project_id'])
	op.create_index('idx_analytics_events_event_type', 'analytics_events', ['event_type'])
	op.create_index('idx_analytics_events_created_at', 'analytics_events', ['created_at'])
	op.create_index('idx_analytics_events_episode_created', 'analytics_events', ['episode_id', 'created_at'])
	op.create_index('idx_analytics_events_project_created', 'analytics_events', ['project_id', 'created_at'])

	# Enable RLS on analytics_events table
	op.execute("ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY")
	op.execute("ALTER TABLE analytics_events FORCE ROW LEVEL SECURITY")

	# RLS policy: users can only see events from their own tenant
	op.execute("""
		CREATE POLICY analytics_events_tenant_isolation ON analytics_events
		FOR ALL
		TO podcastfy_app
		USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
		WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
	""")


def downgrade() -> None:
	op.execute("DROP POLICY IF EXISTS analytics_events_tenant_isolation ON analytics_events")
	op.drop_index('idx_analytics_events_project_created', table_name='analytics_events')
	op.drop_index('idx_analytics_events_episode_created', table_name='analytics_events')
	op.drop_index('idx_analytics_events_created_at', table_name='analytics_events')
	op.drop_index('idx_analytics_events_event_type', table_name='analytics_events')
	op.drop_index('idx_analytics_events_project', table_name='analytics_events')
	op.drop_index('idx_analytics_events_episode', table_name='analytics_events')
	op.drop_index('idx_analytics_events_tenant', table_name='analytics_events')
	op.drop_table('analytics_events')
