"""Generation router for podcast generation and progress tracking"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..config import settings
from ..database import get_db, get_streaming_session_factory, set_tenant_context
from ..models.episode import Episode
from ..models.project import Project
from ..models.content_source import ContentSource
from ..models.user import User
from ..dependencies import get_current_user
from ..services.distribution_target_service import (
    get_active_distribution_targets_for_project,
)
from ..services.rss_generation_service import RSSGenerationService
from ..tasks.podcast_generation import generate_podcast_task
from ..tasks.callbacks import on_workflow_failure

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generation", tags=["Generation"])

# Statuses from which a (re)generation may be started. Anything else means a run
# is already in flight (queued/extracting/generating/uploading/composing/
# distributing/…); starting a second run would race to write s3_url/s3_key/
# generation_status and overwrite the in-progress celery_task_id in
# generation_progress, so SSE would only track the newer task (issue #214).
_RESTARTABLE_STATUSES = frozenset(
    {"draft", "complete", "failed", "distribution_failed"}
)

# File-backed sources (s3_key): the engine takes text, so these cannot be
# generated from until extraction has finished.
_FILE_SOURCE_TYPES = ("pdf", "file", "image")
# Where url / youtube / text sources keep their raw value in source_data.
_RAW_SOURCE_FIELD = {"url": "url", "youtube": "url", "text": "content"}
_RSS_PLATFORM_NAMES = {"spotify": "Spotify", "apple_podcasts": "Apple Podcasts"}


async def _load_restartable_episode(db: AsyncSession, episode_id: UUID, tenant_id) -> Episode:
    """The tenant's episode, or 404; 409 while a run is already in flight."""
    # Eager-load the template relationships so they resolve without a lazy load
    # in the async context.
    result = await db.execute(
        select(Episode)
        .where(
            Episode.id == episode_id,
            Episode.tenant_id == tenant_id,
        )
        .options(
            joinedload(Episode.template),
            joinedload(Episode.project).joinedload(Project.default_template),
        )
    )
    episode = result.unique().scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Only draft/complete/failed episodes are restartable. Checked before any
    # content assembly or dispatch so a duplicate submission cannot race the
    # in-progress task (issue #214).
    if episode.generation_status not in _RESTARTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Generation already in progress for this episode "
                f"(status: {episode.generation_status}); wait for it to finish or fail "
                "before submitting again."
            ),
        )
    return episode


def _raw_source_value(source: ContentSource):
    """The url or pasted text of a source whose extraction has not completed."""
    if source.extraction_status != "complete":
        logger.warning(
            f"Content source {source.id} extraction_status="
            f"'{source.extraction_status}' — falling back to source_data"
        )
    value = source.source_data.get(_RAW_SOURCE_FIELD.get(source.source_type))
    if not (isinstance(value, str) and value.strip()):
        return None
    return value if source.source_type == "text" else value.strip()


def _source_input(source: ContentSource) -> tuple:
    """``(bucket, value)`` for one source: "text", "urls" or "unextracted".

    Extracted content (from ContentExtractionService) is preferred over raw
    source_data; YouTube URLs flow through ``urls``.
    """
    if source.extraction_status == "complete" and source.extracted_content:
        logger.info(
            f"Using extracted content for source {source.id} "
            f"({source.source_type}, {len(source.extracted_content)} chars)"
        )
        return "text", source.extracted_content
    if source.source_type in _FILE_SOURCE_TYPES:
        return "unextracted", str(source.id)
    return ("text" if source.source_type == "text" else "urls"), _raw_source_value(source)


def _sort_sources(sources) -> dict:
    buckets: dict = {"urls": [], "text": [], "unextracted": []}
    for source in sources:
        bucket, value = _source_input(source)
        if value:
            buckets[bucket].append(value)
    return buckets


async def _collect_generation_inputs(db: AsyncSession, episode_id: UUID) -> tuple:
    """``(urls, text_content)`` from the episode's sources, or 400."""
    content_result = await db.execute(
        select(ContentSource).where(ContentSource.episode_id == episode_id)
    )
    content_sources = content_result.scalars().all()

    if not content_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode must have at least one content source"
        )

    inputs = _sort_sources(content_sources)

    if inputs["unextracted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "File sources must finish extraction before generation. "
                f"Pending extraction for source(s): {', '.join(inputs['unextracted'])}"
            ),
        )

    # Guard against queuing an empty job: every source may have been skipped above
    # (e.g. source_data mutated via the update path to drop its url/content key, which
    # is not re-validated). Without usable urls or text there is nothing to generate.
    if not inputs["urls"] and not inputs["text"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No usable content found in the episode's sources; nothing to generate.",
        )
    return inputs["urls"], inputs["text"]


def _conversation_config(episode: Episode):
    """The effective conversation template's config: the episode's, else the
    project default (issue #217), else None so the engine uses its defaults.

    The TTS configuration is not sent: the task reads it from the episode row.
    """
    project = episode.project
    template = episode.template or (project.default_template if project else None)
    # config is JSONB, dict-validated on write (Pydantic); a non-dict value from
    # the store degrades to "use defaults" instead of raising at dispatch time.
    if template and isinstance(template.config, dict):
        return dict(template.config)
    return None


def _distribution_enabled(requested: bool, episode_id: UUID) -> bool:
    """A per-request flag is only honoured when the feature is globally enabled.

    Distribution also requires a publicly reachable audio URL, i.e. an S3
    bucket. With no bucket the workflow-chain path would schedule an invalid
    empty-bucket upload and fail the whole run, whereas the default finalization
    path degrades gracefully, so distribution is only enabled with a bucket.
    """
    enabled = requested and settings.ENABLE_PLATFORM_DISTRIBUTION
    if enabled and not settings.AWS_S3_BUCKET:
        logger.warning(
            "Episode %s: distribution requested but AWS_S3_BUCKET is not configured "
            "— skipping distribution.",
            episode_id,
        )
        return False
    return enabled


async def _platform_map(db: AsyncSession, episode: Episode) -> dict:
    """Platform type → (still encrypted) config for the project's active targets.

    Without this the distribution stage is unreachable (issue #211): the task
    gates it on ``enable_distribution and bool(platforms)``. The task decrypts
    the configs.
    """
    active_targets = await get_active_distribution_targets_for_project(
        db, episode.project_id
    )
    if not active_targets:
        logger.info(
            "Episode %s: distribution requested but no active targets for "
            "project %s — skipping distribution.",
            episode.id, episode.project_id,
        )
        return {}
    # platforms is keyed by platform type (the task's contract), so it
    # holds at most one config per type. When several active targets share
    # a type, prefer the project-scoped one over an account-level
    # (project_id IS NULL) target, then the newest — so an explicit project
    # target always wins over a global default and we never publish to the
    # wrong destination. Dropped same-type duplicates are logged rather than
    # collapsed silently (multi-target-per-type distribution is a follow-up).
    # The query returns newest-first; a stable sort by "is account-level"
    # keeps project-scoped targets ahead while preserving newest-first order.
    platforms: dict = {}
    for target in sorted(active_targets, key=lambda t: t.project_id is None):
        if target.target_type in platforms:
            logger.warning(
                "Episode %s: multiple active %s targets apply to project %s; "
                "using the preferred target and skipping target %s.",
                episode.id, target.target_type, episode.project_id, target.id,
            )
            continue
        platforms[target.target_type] = target.config
    return platforms


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


async def _distribution_plan(db: AsyncSession, episode: Episode, user_id, requested: bool) -> tuple:
    """``(enable_distribution, platforms, warnings)`` for this run."""
    if not _distribution_enabled(requested, episode.id):
        return False, {}, []
    platforms = await _platform_map(db, episode)
    # RSS pre-flight (issue #378): under the RSS-feed model, the distribution
    # task fails permanently for Spotify/Apple when the project has no
    # generated feed. This router is async (unlike the sync Celery task), so
    # auto-generating the feed here is one awaited service call. If it can't be
    # generated (e.g. podcast metadata missing), skip those platforms and tell
    # the caller instead of dispatching a guaranteed distribution_failed.
    rss_platforms = _rss_platforms(platforms)
    if not rss_platforms:
        return True, platforms, []
    exc = await _rss_preflight_error(db, episode, user_id, rss_platforms)
    if exc is None:
        return True, platforms, []
    return True, platforms, [_skip_rss_platforms(platforms, rss_platforms, exc, episode)]


def _task_kwargs(episode: Episode, urls: list, text_content: list, platforms: dict, **flags) -> dict:
    """Only resolved config is passed; omitted kwargs keep the task's defaults."""
    kwargs = {
        "episode_id": str(episode.id),
        "urls": urls or None,
        "text_content": "\n\n".join(text_content) if text_content else None,
        **flags,
    }
    conversation_config = _conversation_config(episode)
    if conversation_config is not None:
        kwargs["conversation_config"] = conversation_config
    if platforms:
        kwargs["platforms"] = platforms
    return kwargs


async def _enqueue_generation(db: AsyncSession, episode: Episode, task_kwargs: dict) -> str:
    """Mark the episode queued, dispatch the task, and return its id (or 503)."""
    # Commit 'queued' BEFORE dispatch so the worker's #295 idempotency guard never
    # observes the pre-regeneration status (e.g. 'complete') and skip a legitimate
    # run. The task id is pre-generated and passed to apply_async so the status can
    # be persisted with celery_task_id ahead of enqueue. Stamp task_started_at so
    # the beat reaper can detect a genuinely-stuck run by age (issue #294).
    # Snapshot the prior (restartable) state so an enqueue failure can restore it
    # rather than clobbering a still-valid 'complete' episode (issue #295).
    prior_status = episode.generation_status
    prior_progress = episode.generation_progress

    new_task_id = str(uuid4())
    episode.generation_status = "queued"
    episode.task_started_at = datetime.now(timezone.utc)
    episode.generation_progress = {
        "stage": "queued",
        "progress": 0,
        "celery_task_id": new_task_id,
    }
    await db.commit()

    # Start Celery task. apply_async (not .delay) so we can attach a link_error:
    # if the task is hard-killed (time limit) or crashes before its own except
    # handler runs, on_workflow_failure still flips the episode to 'failed' instead
    # of leaving it stuck at 'queued' forever (issue #294).
    try:
        generate_podcast_task.apply_async(
            kwargs=task_kwargs,
            task_id=new_task_id,
            link_error=on_workflow_failure.s(
                episode_id=str(episode.id), task_name="generate_podcast"
            ),
        )
    except Exception as exc:  # noqa: BLE001 — the episode was already committed as 'queued', so any enqueue failure must restore the prior restartable status; leaving it queued would strand it until the reaper (#295)
        # Enqueue failed (broker down/rejected) AFTER we committed 'queued'. Restore
        # the prior restartable status so the episode is immediately retryable and a
        # still-valid 'complete' episode stays downloadable — not stuck 'queued'
        # until the reaper, nor wrongly marked 'failed' (issue #295).
        logger.error("Failed to enqueue generation for episode %s: %s", episode.id, exc)
        episode.generation_status = prior_status
        episode.generation_progress = prior_progress
        episode.task_started_at = None
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not start generation (task queue unavailable); please retry.",
        )
    return new_task_id


@router.post("/episodes/{episode_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_podcast(
    episode_id: UUID,
    enable_composition: bool = Query(
        default=False,
        description="Merge audio snippets after generation (requires ENABLE_AUDIO_COMPOSITION)",
    ),
    enable_distribution: bool = Query(
        default=False,
        description="Distribute to platforms after generation (requires ENABLE_PLATFORM_DISTRIBUTION)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start podcast generation for an episode

    Returns HTTP 202 Accepted with task ID for progress tracking
    """
    episode = await _load_restartable_episode(db, episode_id, current_user.tenant_id)
    urls, text_content = await _collect_generation_inputs(db, episode_id)
    use_distribution, platforms, distribution_warnings = await _distribution_plan(
        db, episode, current_user.id, enable_distribution
    )
    new_task_id = await _enqueue_generation(
        db,
        episode,
        _task_kwargs(
            episode, urls, text_content, platforms,
            # Per-request flags are only honoured when the feature is globally enabled.
            enable_composition=enable_composition and settings.ENABLE_AUDIO_COMPOSITION,
            enable_distribution=use_distribution,
        ),
    )

    response = {
        "episode_id": str(episode_id),
        "task_id": new_task_id,
        "status": "queued",
        "message": "Podcast generation started",
    }
    if distribution_warnings:
        response["warnings"] = distribution_warnings
    return response


@router.get("/episodes/{episode_id}/progress")
async def get_generation_progress_stream(
    episode_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_streaming_session_factory),
):
    """
    Server-Sent Events (SSE) endpoint for real-time generation progress

    Streams progress updates as they occur during podcast generation.

    Authentication: standard ``Authorization: Bearer`` header only. The browser
    ``EventSource`` API cannot set custom headers, so the web client reaches this
    endpoint through a same-origin Next.js proxy that injects the header
    server-side. JWTs are never accepted in the URL/query string, since tokens in
    URLs leak into proxy/access logs, browser history, and Referer headers
    (issue #212).
    """
    # Verify episode access
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Capture id + tenant only: the request-scoped `db` session must not be
    # reused inside the long-lived generator. Each poll opens its own
    # short-lived session so a client disconnect can never leave a session
    # checked out of the pool (issue #220).
    stream_episode_id = episode.id
    stream_tenant_id = str(current_user.tenant_id)

    async def event_generator():
        """Generate SSE events with progress updates"""
        try:
            while True:
                # Fresh short-lived session per poll — released by __aexit__.
                async with session_factory() as session:
                    # Re-apply tenant context: unlike the request session, a
                    # fresh session has no app.tenant_id set, so FORCE ROW LEVEL
                    # SECURITY would hide the episode without this (issue #220).
                    await set_tenant_context(session, stream_tenant_id)
                    current = await session.get(Episode, stream_episode_id)

                if current is None:
                    break

                progress_data = {
                    "episode_id": str(current.id),
                    "status": current.generation_status,
                    "progress": current.generation_progress,
                }

                # Send SSE event
                yield f"data: {json.dumps(progress_data)}\n\n"

                # Check if generation reached a terminal status
                if current.generation_status in [
                    "complete",
                    "failed",
                    "distribution_failed",
                ]:
                    break

                # Wait before next update (poll every 2 seconds)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            # Raised when the client disconnects; per-iteration sessions are
            # already released, so just log and let the cancellation propagate.
            logger.info("SSE progress stream cancelled for episode %s", stream_episode_id)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/episodes/{episode_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_podcast(
    episode_id: UUID,
    enable_composition: bool = Query(
        default=False,
        description="Merge audio snippets after generation (requires ENABLE_AUDIO_COMPOSITION)",
    ),
    enable_distribution: bool = Query(
        default=False,
        description="Distribute to platforms after generation (requires ENABLE_PLATFORM_DISTRIBUTION)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate podcast for an episode

    Restarts the generation process by delegating to ``generate_podcast``, which
    validates the episode's content sources and resets ``generation_status`` to
    ``"queued"`` with fresh progress.

    We intentionally do NOT pre-reset the episode to ``"draft"`` before delegating.
    ``generate_podcast`` can raise (404 missing episode, 400 no usable content)
    before it queues anything; committing a status/progress reset first would leave
    the episode degraded on those failures (issue #213). Delegating directly keeps
    the episode untouched unless generation is actually queued.
    """
    # Delegate with explicit keyword arguments. ``generate_podcast`` inserts the
    # ``enable_composition`` / ``enable_distribution`` Query params between
    # ``episode_id`` and ``current_user``; positional binding would misalign the
    # arguments and pass the Depends() sentinels as ``current_user`` / ``db``.
    return await generate_podcast(
        episode_id=episode_id,
        enable_composition=enable_composition,
        enable_distribution=enable_distribution,
        current_user=current_user,
        db=db,
    )
