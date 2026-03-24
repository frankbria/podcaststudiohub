"""Add team collaboration tables

Revision ID: 009
Revises: 008
Create Date: 2026-03-24 00:00:00.000000

Creates three new tables to support team-based collaboration:
  - teams: team/organization records
  - team_members: user membership with role assignment
  - team_invitations: pending email invitations with token-based acceptance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# --- teams table ---
	op.create_table(
		"teams",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("name", sa.String(255), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("logo_url", sa.Text(), nullable=True),
		sa.Column("tier", sa.String(50), nullable=False, server_default="free"),
		sa.Column("stripe_customer_id", sa.String(255), nullable=True),
		sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("stripe_customer_id", name="uq_teams_stripe_customer_id"),
	)

	# --- team_members table ---
	op.create_table(
		"team_members",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
		sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("status", sa.String(50), nullable=False, server_default="active"),
		sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("invited_at", sa.DateTime(), nullable=True),
		sa.Column("last_activity", sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
		sa.UniqueConstraint("team_id", "user_id", name="uq_team_user"),
	)
	op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
	op.create_index("ix_team_members_user_id", "team_members", ["user_id"])

	# --- team_invitations table ---
	op.create_table(
		"team_invitations",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("inviter_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("email", sa.String(255), nullable=False),
		sa.Column("role", sa.String(50), nullable=False, server_default="editor"),
		sa.Column("token", sa.String(255), nullable=False),
		sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
		sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("expires_at", sa.DateTime(), nullable=False),
		sa.Column("accepted_at", sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
		sa.UniqueConstraint("token", name="uq_team_invitations_token"),
	)
	op.create_index("ix_team_invitations_team_id", "team_invitations", ["team_id"])

	# Grant permissions to the app role used by tests/runtime
	op.execute("GRANT ALL ON teams TO podcastfy_app")
	op.execute("GRANT ALL ON team_members TO podcastfy_app")
	op.execute("GRANT ALL ON team_invitations TO podcastfy_app")


def downgrade() -> None:
	op.drop_table("team_invitations")
	op.drop_table("team_members")
	op.drop_table("teams")
