"""
Periodic maintenance tasks.

``reap_stuck_episodes`` is the final safety net for issue #294: if a generation
run slips past every in-task guard (worker crash, broker loss, OOM kill) the
episode can sit in a non-terminal ``generation_status`` forever and the UI shows
a perpetual 'queued'. This beat task fails any episode whose run started longer
ago than ``EPISODE_REAP_THRESHOLD_SECONDS``.

``drain_storage_deletion_outbox`` is the GC worker for issue #366: delete flows
(delete_episode, erase_user) insert a row per S3 key / local file path into the
durable ``storage_deletion_outbox`` table instead of deleting from storage
inline, so a failed commit never leaves storage deleted out from under a row
that's still there. This task retries the actual deletion until it succeeds.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from celery import Task
from sqlalchemy import and_, or_, select

from src.config import settings
from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.storage_deletion_outbox import StorageDeletionOutbox
from src.services.storage_service import StorageService
from src.tasks.callbacks import _update_episode, _utcnow_iso
from src.utils.datetime_utils import utcnow
from src.worker import celery_app

logger = logging.getLogger(__name__)

# Rows fetched per drain iteration. The task loops while a full batch was
# processed, so a backlog larger than this drains in one invocation.
STORAGE_GC_BATCH_SIZE = 100

# Statuses that represent an in-flight run. 'draft' is excluded (not started),
# as are the terminal 'complete'/'failed'.
NON_TERMINAL_STATUSES = (
    "queued",
    "extracting",
    "generating",
    "synthesizing",
    "uploading",
    "composing",
    "distributing",
)


@celery_app.task(bind=True, name="reap_stuck_episodes")
def reap_stuck_episodes(self: Task) -> int:
    """Fail episodes stuck in a non-terminal status past the reap threshold.

    Returns the number of episodes reaped.
    """
    threshold = settings.EPISODE_REAP_THRESHOLD_SECONDS
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold)
    # task_started_at is tz-aware; updated_at is naive UTC. Compare each against a
    # matching-kind cutoff. Prefer task_started_at (stamped at dispatch); fall back
    # to updated_at for rows predating that stamp.
    cutoff_naive = cutoff.replace(tzinfo=None)

    with SyncSessionLocal() as db:
        stuck = db.execute(
            select(Episode.id).where(
                Episode.generation_status.in_(NON_TERMINAL_STATUSES),
                or_(
                    and_(
                        Episode.task_started_at.isnot(None),
                        Episode.task_started_at < cutoff,
                    ),
                    and_(
                        Episode.task_started_at.is_(None),
                        Episode.updated_at < cutoff_naive,
                    ),
                ),
            )
        ).scalars().all()

    reaped = 0
    for episode_id in stuck:
        updated = _update_episode(
            str(episode_id),
            updates={"generation_status": "failed"},
            progress_updates={
                "status": "failed",
                "error_message": f"Reaped: exceeded max runtime ({threshold}s)",
                "failed_at": _utcnow_iso(),
            },
        )
        if updated:
            reaped += 1

    if reaped:
        logger.warning("Reaped %d stuck episode(s) past %ds threshold", reaped, threshold)
    return reaped


@celery_app.task(bind=True, name="drain_storage_deletion_outbox")
def drain_storage_deletion_outbox(self: Task) -> int:
    """Retry queued storage deletions until they succeed (issue #366).

    Batch-fetches rows with ``FOR UPDATE SKIP LOCKED`` so an overlapping
    invocation (beat tick racing a delete flow's post-commit trigger) skips
    rows already claimed instead of double-processing them. Deletion is
    idempotent both ways (a missing local file, or a repeated S3
    ``delete_object``, both count as success — issue #366 AC5), so a row is
    only removed once every key/path it names is gone. A failure increments
    ``attempts``/``last_attempt_at`` and leaves the row queued for the next
    drain; no ``self.retry`` is used here since the beat schedule and the
    delete flows' prompt trigger both already re-run this task.

    Loops while a full batch was processed so a backlog drains in one
    invocation. Returns the total number of rows successfully drained.
    """
    storage: StorageService | None = None
    drained = 0

    while True:
        with SyncSessionLocal() as db:
            rows = db.execute(
                select(StorageDeletionOutbox)
                .order_by(StorageDeletionOutbox.created_at)
                .with_for_update(skip_locked=True)
                .limit(STORAGE_GC_BATCH_SIZE)
            ).scalars().all()

            if not rows:
                break

            for row in rows:
                ok = True

                if row.s3_key:
                    if storage is None:
                        storage = StorageService()
                    try:
                        asyncio.run(storage.delete_file(row.s3_key))
                    except Exception as exc:
                        ok = False
                        logger.warning(
                            "Failed to delete S3 object %s (attempt %d): %s",
                            row.s3_key, row.attempts + 1, exc,
                        )

                if ok and row.file_path:
                    try:
                        os.remove(row.file_path)
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        ok = False
                        logger.warning(
                            "Failed to remove local file %s (attempt %d): %s",
                            row.file_path, row.attempts + 1, exc,
                        )

                if ok:
                    db.delete(row)
                    drained += 1
                else:
                    row.attempts += 1
                    row.last_attempt_at = utcnow()

            db.commit()

            if len(rows) < STORAGE_GC_BATCH_SIZE:
                break

    if drained:
        logger.info("Drained %d storage deletion(s) from the outbox", drained)
    return drained
