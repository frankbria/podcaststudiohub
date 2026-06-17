"""Generation router for podcast generation and progress tracking"""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..config import settings
from ..database import get_db
from ..models.episode import Episode
from ..models.project import Project
from ..models.content_source import ContentSource
from ..models.user import User
from ..dependencies import get_current_user
from ..services.distribution_target_service import (
    get_active_distribution_targets_for_project,
)
from ..tasks.podcast_generation import generate_podcast_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generation", tags=["Generation"])

# podcastfy 0.4.1's TTSProviderFactory registers providers as
# {openai, elevenlabs, edge, gemini, geminimulti}. The app stores the
# multi-speaker provider as "gemini_multi" (underscore), which podcastfy would
# reject as unsupported — normalize it before forwarding (issue #217).
_PODCASTFY_TTS_PROVIDER = {"gemini_multi": "geminimulti"}

# Statuses from which a (re)generation may be started. Anything else means a run
# is already in flight (queued/extracting/generating/uploading/composing/
# distributing/…); starting a second run would race to write s3_url/s3_key/
# generation_status and overwrite the in-progress celery_task_id in
# generation_progress, so SSE would only track the newer task (issue #214).
_RESTARTABLE_STATUSES = frozenset({"draft", "complete", "failed"})


def _podcastfy_tts_model(provider: str) -> str:
    """Map a stored TTS provider name to podcastfy's expected provider key."""
    return _PODCASTFY_TTS_PROVIDER.get(provider, provider)


def _podcastfy_text_to_speech(provider: str, config: dict) -> dict:
    """Translate a stored TTS config into podcastfy's ``text_to_speech`` schema.

    The app persists a flat per-provider dict (``model`` plus ``voice_1``/
    ``voice_2`` or ``voice_1_id``/``voice_2_id``), but podcastfy 0.4.1 reads
    ``text_to_speech.<provider>.default_voices.{question,answer}`` and
    ``text_to_speech.<provider>.model``. Without this mapping the user's voice/
    model selection lands on keys podcastfy never reads and is silently ignored.
    """
    pf_provider = _podcastfy_tts_model(provider)
    question = config.get("voice_1") or config.get("voice_1_id")
    answer = config.get("voice_2") or config.get("voice_2_id")

    provider_block: dict = {}
    voices = {}
    if question:
        voices["question"] = question
    if answer:
        voices["answer"] = answer
    if voices:
        provider_block["default_voices"] = voices
    if config.get("model"):
        provider_block["model"] = config["model"]

    return {"default_tts_model": pf_provider, pf_provider: provider_block}


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
    # Get episode, eager-loading the TTS/template config relationships so they
    # can be resolved below without triggering lazy loads in the async context.
    result = await db.execute(
        select(Episode)
        .where(
            Episode.id == episode_id,
            Episode.tenant_id == current_user.tenant_id,
        )
        .options(
            joinedload(Episode.tts_config),
            joinedload(Episode.template),
            joinedload(Episode.project).joinedload(Project.default_tts_config),
            joinedload(Episode.project).joinedload(Project.default_template),
        )
    )
    episode = result.unique().scalar_one_or_none()

    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    # Reject if a run is already in flight: only draft/complete/failed episodes are
    # restartable. Checked before any content assembly or dispatch so a duplicate
    # submission cannot race the in-progress task (issue #214).
    if episode.generation_status not in _RESTARTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Generation already in progress for this episode "
                f"(status: {episode.generation_status}); wait for it to finish or fail "
                "before submitting again."
            ),
        )

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

    # Resolve the effective TTS config and conversation template: prefer the
    # episode-level override, then fall back to the project default. Without this
    # the task always used its default tts_model ('openai'), silently ignoring the
    # user's selection (issue #217).
    project = episode.project
    effective_tts = episode.tts_config or (project.default_tts_config if project else None)
    effective_template = episode.template or (project.default_template if project else None)

    tts_model = _podcastfy_tts_model(effective_tts.provider) if effective_tts else None

    conversation_config = None
    if effective_template or effective_tts:
        conversation_config = {}
        # config columns are JSONB; they are dict-validated on write (Pydantic),
        # but guard against a non-dict value from the store so a corrupt row
        # degrades to "use defaults" instead of raising at dispatch time.
        if effective_template and isinstance(effective_template.config, dict):
            conversation_config.update(effective_template.config)
        if effective_tts and isinstance(effective_tts.config, dict):
            conversation_config["text_to_speech"] = _podcastfy_text_to_speech(
                effective_tts.provider, effective_tts.config
            )

    # Only pass resolved config kwargs; omit them so the task keeps its defaults
    # (tts_model='openai', conversation_config=None) for unconfigured episodes.
    extra_kwargs = {}
    if tts_model is not None:
        extra_kwargs["tts_model"] = tts_model
    if conversation_config is not None:
        extra_kwargs["conversation_config"] = conversation_config

    # Load active distribution targets and build the platforms mapping so the
    # distribution stage actually fires (issue #211): the task gates distribution
    # on `enable_distribution and bool(platforms)`, so without this the subsystem
    # is unreachable. Configs stay encrypted here; the task decrypts them.
    # Distribution requires a publicly reachable audio URL, i.e. an S3 bucket. With
    # no bucket the workflow-chain path would schedule an invalid empty-bucket
    # upload and fail the whole run, whereas the default finalization path degrades
    # gracefully — so only enable distribution when a bucket is configured.
    if use_distribution and not settings.AWS_S3_BUCKET:
        logger.warning(
            "Episode %s: distribution requested but AWS_S3_BUCKET is not configured "
            "— skipping distribution.",
            episode_id,
        )
        use_distribution = False

    if use_distribution:
        active_targets = await get_active_distribution_targets_for_project(
            db, episode.project_id
        )
        if active_targets:
            # platforms is keyed by platform type (the task's contract), so it
            # holds at most one config per type. When several active targets share
            # a type, prefer the project-scoped one over an account-level
            # (project_id IS NULL) target, then the newest — so an explicit project
            # target always wins over a global default and we never publish to the
            # wrong destination. Dropped same-type duplicates are logged rather than
            # collapsed silently (multi-target-per-type distribution is a follow-up).
            # The query returns newest-first; a stable sort by "is account-level"
            # keeps project-scoped targets ahead while preserving newest-first order.
            ordered_targets = sorted(active_targets, key=lambda t: t.project_id is None)
            platforms: dict = {}
            for target in ordered_targets:
                if target.target_type in platforms:
                    logger.warning(
                        "Episode %s: multiple active %s targets apply to project %s; "
                        "using the preferred target and skipping target %s.",
                        episode_id, target.target_type, episode.project_id, target.id,
                    )
                    continue
                platforms[target.target_type] = target.config
            extra_kwargs["platforms"] = platforms
        else:
            logger.info(
                "Episode %s: distribution requested but no active targets for "
                "project %s — skipping distribution.",
                episode_id, episode.project_id,
            )

    # Start Celery task
    task = generate_podcast_task.delay(
        episode_id=str(episode_id),
        urls=urls if urls else None,
        text_content="\n\n".join(text_content) if text_content else None,
        enable_composition=use_composition,
        enable_distribution=use_distribution,
        **extra_kwargs,
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
