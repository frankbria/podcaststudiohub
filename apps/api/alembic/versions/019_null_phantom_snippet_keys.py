"""Null the phantom audio_snippets.s3_key values written before #536

Before #536, upload_audio_snippet generated the S3 key before calling S3 and
persisted it even when AWS_S3_BUCKET was unset and nothing was uploaded, so
rows created in an environment without S3 carry a key for an object that never
existed (issue #537). Since #536 snippet deletion, and since #366 account
erasure, queue `s3_key` in storage_deletion_outbox, where such a key can never
drain: `attempts` grows on every beat tick and a warning is logged each time.

`s3_url` is set on every real upload (StorageService.upload_file returns it),
so `s3_key IS NOT NULL AND s3_url IS NULL` is a phantom key.

Order matters: the queued deletions are matched against the phantom keys
before those keys are nulled. Both statements are idempotent, so a rerun is a
no-op (#318). Data-only; there is no DDL to run concurrently.

Revision ID: 019
Revises: 018
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PHANTOM = "s3_key IS NOT NULL AND s3_url IS NULL"


def upgrade() -> None:
    bind = op.get_bind()
    # Both tables are under FORCE RLS for the app role. A migration runs as a
    # role that may bypass it; with row_security=off a no-bypass role errors
    # instead of silently touching only the rows of no tenant (#301).
    bind.execute(sa.text("SET LOCAL row_security = off"))
    bind.execute(sa.text(
        f"DELETE FROM storage_deletion_outbox "
        f"WHERE s3_key IN (SELECT s3_key FROM audio_snippets WHERE {PHANTOM})"
    ))
    bind.execute(sa.text(f"UPDATE audio_snippets SET s3_key = NULL WHERE {PHANTOM}"))


def downgrade() -> None:
    # Irreversible data fix: the nulled keys named objects that never existed,
    # so there is nothing meaningful to restore.
    pass
