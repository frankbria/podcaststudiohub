"""Which platforms a distribution run publishes to (#211, #378, #625).

Shared by generation (the router) and by approval of a held episode, so both
resolve targets and run the RSS pre-flight the same way.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.episode import Episode
from .distribution_target_service import active_platform_map
from .rss_generation_service import RSSGenerationService

logger = logging.getLogger(__name__)

_RSS_PLATFORM_NAMES = {"spotify": "Spotify", "apple_podcasts": "Apple Podcasts"}


def _rss_platforms(platforms: dict) -> list:
    """The platforms that ingest through the project's RSS feed."""
    if settings.ENABLE_DIRECT_PLATFORM_PUBLISH:
        return []
    return [p for p in _RSS_PLATFORM_NAMES if p in platforms]


async def _ensure_rss_feed(db: AsyncSession, episode: Episode, user_id, rss_platforms: list) -> None:
    rss_service = RSSGenerationService()
    feed = await rss_service.get_rss_feed(db, episode.project_id)
    if feed is None or not feed.public_url:
        await rss_service.generate_rss_for_project(db, episode.project_id, user_id)
        logger.info(
            "Episode %s: auto-generated missing RSS feed for "
            "project %s ahead of %s distribution.",
            episode.id, episode.project_id, ", ".join(rss_platforms),
        )


async def _rss_preflight_error(db: AsyncSession, episode: Episode, user_id, rss_platforms: list):
    """Make sure the project has a feed; return what went wrong, or None.

    Non-fatal: a failure here must skip the RSS-model platforms with a
    warning, never 500 the generation kickoff itself. It runs under a
    SAVEPOINT so a DB-level failure (e.g. the unique-RSSFeed race between two
    concurrent generations) aborts only the pre-flight work: a whole-session
    rollback would poison the later 'queued' commit path by expiring loaded
    instances (and, under the test harness's shared-session wrapping, wipe
    prior writes).
    """
    preflight_sp = await db.begin_nested()
    try:
        await _ensure_rss_feed(db, episode, user_id, rss_platforms)
        # The service commits internally on success, consuming the
        # savepoint; release it only if it is still open.
        if preflight_sp.is_active:
            await preflight_sp.commit()
        return None
    except Exception as exc:  # noqa: BLE001 — the savepoint must be rolled back and the RSS platforms dropped whatever failed, and only ValueError's message is user-safe — anything else stays internal so infrastructure details never leak
        if preflight_sp.is_active:
            await preflight_sp.rollback()
        return exc


def _skip_rss_platforms(platforms: dict, rss_platforms: list, exc: Exception, episode: Episode) -> str:
    """Drop the RSS-model platforms and return the warning for the caller."""
    for p in rss_platforms:
        del platforms[p]
    # ValueError carries a user-actionable validation message
    # (same contract as the RSS router's 422); anything else
    # stays internal so infrastructure details never leak.
    reason = (
        str(exc) if isinstance(exc, ValueError)
        else "feed generation failed unexpectedly"
    )
    skipped = " and ".join(_RSS_PLATFORM_NAMES[p] for p in rss_platforms)
    logger.warning(
        "Episode %s: RSS pre-flight failed for project %s; "
        "skipping %s distribution: %s",
        episode.id, episode.project_id,
        ", ".join(rss_platforms), exc,
    )
    return (
        f"Skipped {skipped} distribution: "
        "these platforms ingest episodes via the project's RSS "
        f"feed, which has not been generated and could not be "
        f"auto-generated ({reason}). Set the podcast metadata "
        "and generate the feed from the project's distribution "
        "page, then regenerate."
    )


async def plan_platforms(db: AsyncSession, episode: Episode, user_id) -> tuple:
    """``(platforms, warnings)``: the project's active targets, minus any RSS-model
    platform whose feed could not be made ready.

    RSS pre-flight (issue #378): under the RSS-feed model, the distribution
    task fails permanently for Spotify/Apple when the project has no generated
    feed. Callers are async (unlike the sync Celery task), so auto-generating
    the feed here is one awaited service call. If it can't be generated (e.g.
    podcast metadata missing), those platforms are skipped and the caller is
    told, instead of dispatching a guaranteed distribution_failed.

    May commit: the feed service commits a generated feed itself.
    """
    platforms = await active_platform_map(db, episode)
    rss_platforms = _rss_platforms(platforms)
    if not rss_platforms:
        return platforms, []
    exc = await _rss_preflight_error(db, episode, user_id, rss_platforms)
    if exc is None:
        return platforms, []
    return platforms, [_skip_rss_platforms(platforms, rss_platforms, exc, episode)]
