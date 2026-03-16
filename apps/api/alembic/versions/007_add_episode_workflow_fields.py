"""Add workflow tracking fields to episodes table

Adds platform_ids (JSONB) and error_message (Text) columns to the episodes
table to support the full podcast generation workflow including platform
distribution tracking and structured error reporting.

Revision ID: 007
Revises: 006
Create Date: 2026-03-16 00:00:00.000000

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
	op.add_column(
		'episodes',
		sa.Column(
			'platform_ids',
			postgresql.JSONB(astext_type=sa.Text()),
			nullable=False,
			server_default='{}',
		),
	)
	op.add_column(
		'episodes',
		sa.Column('error_message', sa.Text(), nullable=True),
	)


def downgrade() -> None:
	op.drop_column('episodes', 'error_message')
	op.drop_column('episodes', 'platform_ids')
