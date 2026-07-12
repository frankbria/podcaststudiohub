"""
Post-completion RSS feed refresh (issue #382).

When an episode reaches ``complete``, the project's RSS feed XML on S3 is
stale — platforms consuming it (Spotify/Apple under the RSS-feed distribution
model) would never see the new episode. Both episode-completion sites
(``on_workflow_complete`` for the workflow chain, and
``finalize_episode_generation_task`` for the no-chain path) call
``refresh_project_rss_feed`` to regenerate it.

The refresh is deliberately best-effort: it never raises, so a feed problem
(incomplete podcast metadata, S3 outage) can never fail an episode that has
already completed. It is also idempotent — the service does a single upsert
per project — so concurrent completions in one project are safe.
"""
import asyncio
import logging
from uuid import UUID

from src.database import celery_async_session
from src.services.rss_generation_service import RSSGenerationService

logger = logging.getLogger(__name__)


def refresh_project_rss_feed(project_id, user_id) -> bool:
    """
    Regenerate the project's RSS feed if one has already been generated.

    Skips projects with no RSSFeed row: no platform consumes their feed yet
    (the #378 distribution pre-flight creates it when distribution starts).

    Args:
        project_id: Project UUID (or string form, as Celery tasks hold).
        user_id: Owning user's UUID, for the service's access check.

    Returns:
        True if the feed was regenerated, False if skipped or failed.
        Never raises.
    """
    try:
        # Normalize before any IO so garbage input can never reach the DB.
        project_uuid = UUID(str(project_id))
        user_uuid = UUID(str(user_id))
        return asyncio.run(_refresh_async(project_uuid, user_uuid))
    except Exception as exc:
        logger.error(
            "RSS feed refresh failed for project %s: %s",
            project_id,
            exc,
            exc_info=True,
        )
        return False


async def _refresh_async(project_id: UUID, user_id: UUID) -> bool:
    service = RSSGenerationService()
    async with celery_async_session() as db:
        # Celery sessions don't arm the tenant GUC; like the other task-side
        # queries, isolation comes from the explicit project_id filter.
        feed = await service.get_rss_feed(db, project_id)
        if feed is None:
            logger.info(
                "Project %s has no RSS feed yet; skipping post-completion refresh",
                project_id,
            )
            return False
        await service.generate_rss_for_project(db, project_id, user_id)
    logger.info("RSS feed refreshed for project %s after episode completion", project_id)
    return True
