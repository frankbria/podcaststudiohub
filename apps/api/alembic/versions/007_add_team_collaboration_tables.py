"""Add team collaboration tables: teams, team_members, team_invitations

Creates the data model needed for multi-user team collaboration:
- teams: Organization/team entity with billing tier
- team_members: Many-to-many with role between users and teams
- team_invitations: Pending email invitations with tokens

Revision ID: 007
Revises: 006
Create Date: 2026-03-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	# Create teams table
	op.create_table(
		'teams',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('name', sa.String(255), nullable=False),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('logo_url', sa.Text(), nullable=True),
		sa.Column('tier', sa.String(50), nullable=False, server_default='free'),
		sa.Column('stripe_customer_id', sa.String(), nullable=True),
		sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column('created_at', sa.DateTime(), nullable=False),
		sa.Column('updated_at', sa.DateTime(), nullable=False),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('stripe_customer_id'),
	)

	# Create team_members table
	op.create_table(
		'team_members',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('role', sa.String(50), nullable=False, server_default='viewer'),
		sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column('status', sa.String(50), nullable=False, server_default='active'),
		sa.Column('joined_at', sa.DateTime(), nullable=False),
		sa.Column('invited_at', sa.DateTime(), nullable=True),
		sa.Column('last_activity', sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('team_id', 'user_id', name='uq_team_member_team_user'),
	)
	op.create_index('ix_team_members_team_id', 'team_members', ['team_id'])
	op.create_index('ix_team_members_user_id', 'team_members', ['user_id'])

	# Create team_invitations table
	op.create_table(
		'team_invitations',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('inviter_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('email', sa.String(255), nullable=False),
		sa.Column('role', sa.String(50), nullable=False, server_default='editor'),
		sa.Column('token', sa.String(255), nullable=False),
		sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
		sa.Column('created_at', sa.DateTime(), nullable=False),
		sa.Column('expires_at', sa.DateTime(), nullable=False),
		sa.Column('accepted_at', sa.DateTime(), nullable=True),
		sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
		sa.ForeignKeyConstraint(['inviter_id'], ['users.id']),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('token'),
	)
	op.create_index('ix_team_invitations_team_id', 'team_invitations', ['team_id'])
	op.create_index('ix_team_invitations_token', 'team_invitations', ['token'])


def downgrade() -> None:
	op.drop_index('ix_team_invitations_token', table_name='team_invitations')
	op.drop_index('ix_team_invitations_team_id', table_name='team_invitations')
	op.drop_table('team_invitations')

	op.drop_index('ix_team_members_user_id', table_name='team_members')
	op.drop_index('ix_team_members_team_id', table_name='team_members')
	op.drop_table('team_members')

	op.drop_table('teams')
