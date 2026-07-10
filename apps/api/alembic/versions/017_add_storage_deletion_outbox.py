"""Add storage_deletion_outbox table for durable storage erasure (issue #366)

Revision ID: 017
Revises: 016
Create Date: 2026-07-10 00:00:00.000000

delete_episode and erase_user used to best-effort delete S3/local storage
before committing the DB row delete. Two orphan windows followed: a commit
failure after storage deletion left rows pointing at deleted audio, and a
Celery task finishing after the row was gone re-uploaded audio nobody could
ever find again (no s3:ListBucket). This table is a durable outbox: delete
flows insert a row per key/path in the same transaction as the row delete,
so a failed commit leaves storage untouched, and a periodic GC worker
(drain_storage_deletion_outbox) retries deletion until it succeeds.

Deliberately has NO Row-Level Security: it is never API-exposed, and the GC
worker must drain rows across every tenant in one pass.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		"storage_deletion_outbox",
		sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
		sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("s3_key", sa.Text(), nullable=True),
		sa.Column("file_path", sa.Text(), nullable=True),
		sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
		sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
		sa.CheckConstraint(
			"s3_key IS NOT NULL OR file_path IS NOT NULL",
			name="storage_deletion_outbox_key_or_path_check",
		),
	)

	op.create_index(
		"ix_storage_deletion_outbox_created_at",
		"storage_deletion_outbox",
		["created_at"],
	)

	# Non-superuser app role must be able to read/write this table (issue #308).
	op.execute("GRANT ALL ON storage_deletion_outbox TO podcastfy_app")


def downgrade() -> None:
	op.drop_table("storage_deletion_outbox")
