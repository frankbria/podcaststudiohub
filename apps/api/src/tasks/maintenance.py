"""
Periodic maintenance tasks.

``reap_stuck_episodes`` is the final safety net for issue #294: if a generation
run slips past every in-task guard (worker crash, broker loss, OOM kill) the
episode can sit in a non-terminal ``generation_status`` forever and the UI shows
a perpetual 'queued'. This beat task fails any episode whose run started longer
ago than ``EPISODE_REAP_THRESHOLD_SECONDS``.
"""
import logging
from datetime import datetime, timedelta, timezone

from celery import Task
from sqlalchemy import and_, or_, select

from src.config import settings
from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.tasks.callbacks import _update_episode, _utcnow_iso
from src.worker import celery_app

logger = logging.getLogger(__name__)

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
