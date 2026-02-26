"""Generation router for podcast generation and progress tracking"""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import json

from ..database import get_db
from ..models.episode import Episode
from ..models.content_source import ContentSource
from ..models.user import User
from ..dependencies import get_current_user
from ..middleware.auth import get_current_user_from_query
from ..tasks.podcast_generation import generate_podcast_task

router = APIRouter(prefix="/generation", tags=["Generation"])


@router.post("/episodes/{episode_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_podcast(
    episode_id: UUID,
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

    # Prepare content data
    # Prefer extracted_content (from ContentExtractionService) over raw source_data
    urls = []
    file_paths = []
    text_content = []

    for source in content_sources:
        if source.extraction_status == "complete" and source.extracted_content:
            # Use pre-extracted text for all extractable source types
            text_content.append(source.extracted_content)
            import logging
            logging.getLogger(__name__).info(
                f"Using extracted content for source {source.id} "
                f"({source.source_type}, {len(source.extracted_content)} chars)"
            )
        else:
            # Fall back to raw source_data if extraction hasn't completed
            if source.extraction_status not in ("complete",):
                import logging
                logging.getLogger(__name__).warning(
                    f"Content source {source.id} extraction_status="
                    f"'{source.extraction_status}' — falling back to source_data"
                )
            if source.source_type == "url":
                urls.append(source.source_data.get("url"))
            elif source.source_type == "youtube":
                urls.append(source.source_data.get("url"))
            elif source.source_type == "file":
                file_paths.append(source.source_data.get("s3_key"))
            elif source.source_type == "text":
                text_content.append(source.source_data.get("content"))

    # Start Celery task
    task = generate_podcast_task.delay(
        episode_id=str(episode_id),
        urls=urls if urls else None,
        file_paths=file_paths if file_paths else None,
        text_content="\n\n".join(text_content) if text_content else None,
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
    current_user: User = Depends(get_current_user_from_query),
    db: AsyncSession = Depends(get_db),
):
    """
    Server-Sent Events (SSE) endpoint for real-time generation progress

    Streams progress updates as they occur during podcast generation.

    Authentication: Accepts JWT token via query parameter (?token=<jwt>) to support
    the browser EventSource API, which cannot send custom headers. Falls back to the
    standard Authorization header for backward compatibility.
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

    Resets generation status and restarts the generation process
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

    # Reset generation status
    episode.generation_status = "draft"
    episode.generation_progress = {}
    await db.commit()

    # Call generate endpoint
    return await generate_podcast(episode_id, current_user, db)
