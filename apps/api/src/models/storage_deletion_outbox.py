"""StorageDeletionOutbox model — durable storage-erasure queue (issue #366).

Delete flows (delete_episode, erase_user) insert a row here in the same
transaction as the row delete, instead of best-effort deleting from S3/local
storage before commit. A periodic GC worker (drain_storage_deletion_outbox)
retries deletion until it succeeds and removes the row.

Deliberately has NO Row-Level Security (see migration 017): it is never
API-exposed, and the GC worker must drain rows across every tenant. tenant_id
is kept as a plain nullable UUID (no FK) so a row can outlive the user row it
was queued for.
"""
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..database import Base
from ..utils.datetime_utils import utcnow


class StorageDeletionOutbox(Base):
    """Queued storage deletion: one S3 key or local file path per row."""

    __tablename__ = "storage_deletion_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)

    s3_key = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)

    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_storage_deletion_outbox_created_at", "created_at"),
        CheckConstraint(
            "s3_key IS NOT NULL OR file_path IS NOT NULL",
            name="storage_deletion_outbox_key_or_path_check",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<StorageDeletionOutbox(id={self.id}, s3_key={self.s3_key}, "
            f"file_path={self.file_path}, attempts={self.attempts})>"
        )
