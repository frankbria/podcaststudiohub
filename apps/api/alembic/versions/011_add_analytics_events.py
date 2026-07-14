"""Add analytics_events table for usage tracking

Revision ID: 011
Revises: 010
Create Date: 2026-03-25 00:00:00.000000

Creates the analytics_events table to track download/play/share/stream events
per episode and project, with composite indexes for efficient time-range queries.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"analytics_events",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("event_type", sa.Text(), nullable=False),
		sa.Column("user_agent", sa.Text(), nullable=True),
		sa.Column("referer", sa.Text(), nullable=True),
		sa.Column("ip_address", sa.Text(), nullable=True),
		sa.Column("country", sa.Text(), nullable=True),
		sa.Column("device_type", sa.Text(), nullable=True),
		sa.Column("app_name", sa.Text(), nullable=True),
		sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
	)

	# Indexes for common query patterns.
	# Deliberately NOT CONCURRENTLY (issue #318): analytics_events is created
	# in this same migration, so it is empty and invisible to any other
	# transaction — a plain CREATE INDEX blocks nothing, while CONCURRENTLY
	# would force an autocommit block and add partial-failure modes.
	op.create_index("ix_analytics_events_tenant_id", "analytics_events", ["tenant_id"])
	op.create_index("ix_analytics_events_episode_id", "analytics_events", ["episode_id"])
	op.create_index("ix_analytics_events_project_id", "analytics_events", ["project_id"])
	op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
	op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])
	op.create_index(
		"ix_analytics_events_episode_created",
		"analytics_events",
		["episode_id", "created_at"],
	)
	op.create_index(
		"ix_analytics_events_project_created",
		"analytics_events",
		["project_id", "created_at"],
	)

	# Grant permissions to app role
	op.execute("GRANT ALL ON analytics_events TO podcastfy_app")


def downgrade() -> None:
	op.drop_table("analytics_events")
