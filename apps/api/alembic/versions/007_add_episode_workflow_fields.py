"""Add workflow tracking fields to episodes table

Adds platform_ids (JSONB) and error_message (TEXT) columns to the episodes
table to support the Celery task chaining workflow introduced in GAP-026.

- platform_ids: stores platform-specific episode IDs after distribution
  (e.g. {"spotify": "abc123", "apple_podcasts": "xyz789"})
- error_message: stores error details when generation_status is 'failed'

Revision ID: 007
Revises: 006
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.add_column(
		'episodes',
		sa.Column('platform_ids', JSONB, nullable=True, server_default='{}'),
	)
	op.add_column(
		'episodes',
		sa.Column('error_message', sa.Text, nullable=True),
	)


def downgrade() -> None:
	op.drop_column('episodes', 'error_message')
	op.drop_column('episodes', 'platform_ids')
