"""Generation router for podcast generation and progress tracking"""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import settings
from ..database import get_db
from ..models.episode import Episode
from ..models.content_source import ContentSource
from ..models.user import User
from ..dependencies import get_current_user
from ..tasks.podcast_generation import generate_podcast_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generation", tags=["Generation"])


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
    # Get episode
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
    )
    episode = result.scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Get content sources
    content_result = await db.execute(
        select(ContentSource).where(ContentSource.episode_id == episode_id)
    )
    content_sources = content_result.scalars().all()

    if not content_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode must have at least one content source"
        )

    # Prepare content data.
    # Prefer extracted_content (from ContentExtractionService) over raw source_data.
    # podcastfy 0.4.1 has no kwarg for file paths, so file/PDF sources MUST be
    # pre-extracted into text; YouTube URLs flow through `urls`.
    urls = []
    text_content = []
    unextracted_files = []

    for source in content_sources:
        if source.extraction_status == "complete" and source.extracted_content:
            # Use pre-extracted text for all extractable source types
            text_content.append(source.extracted_content)
            logger.info(
                f"Using extracted content for source {source.id} "
                f"({source.source_type}, {len(source.extracted_content)} chars)"
            )
        elif source.source_type in ("pdf", "file", "image"):
            # File-backed sources (s3_key) without completed extraction cannot be
            # generated: podcastfy cannot read the raw s3_key. Reject so the caller
            # knows extraction must finish first (see HTTP 400 below).
            unextracted_files.append(str(source.id))
        else:
            # url / youtube / text can fall back to raw source_data
            if source.extraction_status != "complete":
                logger.warning(
                    f"Content source {source.id} extraction_status="
                    f"'{source.extraction_status}' — falling back to source_data"
                )
            if source.source_type in ("url", "youtube"):
                url = source.source_data.get("url")
                if isinstance(url, str) and url.strip():
                    urls.append(url.strip())
            elif source.source_type == "text":
                content = source.source_data.get("content")
                if isinstance(content, str) and content.strip():
                    text_content.append(content)

    if unextracted_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "File sources must finish extraction before generation. "
                f"Pending extraction for source(s): {', '.join(unextracted_files)}"
            ),
        )

    # Guard against queuing an empty job: every source may have been skipped above
    # (e.g. source_data mutated via the update path to drop its url/content key, which
    # is not re-validated). Without usable urls or text there is nothing to generate.
    if not urls and not text_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No usable content found in the episode's sources; nothing to generate.",
        )

    # Resolve composition / distribution flags against global feature settings.
    # Per-request flags are only honoured when the feature is globally enabled.
    use_composition = enable_composition and settings.ENABLE_AUDIO_COMPOSITION
    use_distribution = enable_distribution and settings.ENABLE_PLATFORM_DISTRIBUTION

    # Start Celery task
    task = generate_podcast_task.delay(
        episode_id=str(episode_id),
        urls=urls if urls else None,
        text_content="\n\n".join(text_content) if text_content else None,
        enable_composition=use_composition,
        enable_distribution=use_distribution,
    )

    # Update episode status
    episode.generation_status = "queued"
    episode.generation_progress = {
        "stage": "queued",
        "progress": 0,
        "celery_task_id": task.id,
    }
    await db.commit()

    return {
        "episode_id": str(episode_id),
        "task_id": task.id,
        "status": "queued",
        "message": "Podcast generation started",
    }


@router.get("/episodes/{episode_id}/progress")
async def get_generation_progress_stream(
    episode_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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

    async def event_generator():
        """Generate SSE events with progress updates"""
        while True:
            # Refresh episode to get latest progress
            await db.refresh(episode)

            progress_data = {
                "episode_id": str(episode.id),
                "status": episode.generation_status,
                "progress": episode.generation_progress,
            }

            # Send SSE event
            yield f"data: {json.dumps(progress_data)}\n\n"

            # Check if generation is complete or failed
            if episode.generation_status in ["complete", "failed"]:
                break

            # Wait before next update (poll every 2 seconds)
            await asyncio.sleep(2)

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
        enable_composition=False,
        enable_distribution=False,
        current_user=current_user,
        db=db,
    )
