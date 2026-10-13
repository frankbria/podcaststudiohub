"""
Celery tasks for podcast generation.

generate_podcast_task runs the in-repo engine (src/engine, #538 / #543).
"""
import os
import shutil
import tempfile
import time
import uuid as uuid_module
import logging
from pathlib import Path
from celery import Task, chain
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from typing import Optional, List, Dict, Any
from pydub import AudioSegment

from src.worker import celery_app
from src.config import settings
from src.database import SyncSessionLocal
from src.engine import EngineError, generate_script
from src.engine.quality import quality_metrics
from src.engine.screening import screen_script
from src.engine.transcript import persist_transcript
from src.engine.tts import synthesise
from src.engine.tts.base import VoiceConfig
from src.models.audio_snippet import AudioSnippet
from src.models.episode import Episode
from src.services.content_extraction_service import ContentExtractionService
from src.tasks.callbacks import _update_episode, _utcnow_iso, _queue_orphaned_storage
from src.tasks.content_review import episode_held_for_review
from src.tasks.idempotency import acquire_generation_lock, release_generation_lock
from src.tasks.progress import BestEffortProgressTask
from src.tasks.script_cache import load_run, save_run
from src.tasks.rss_refresh import refresh_project_rss_feed
from src.tasks.s3_upload import (
    GENERATION_RUN_DIR_PREFIX,
    _cleanup_temp_file,
    upload_to_s3_task,
)
from src.tasks.retry_utils import calculate_backoff
from src.utils.validators import validate_uuid

logger = logging.getLogger(__name__)

# Active (non-terminal, non-queued) statuses. Seeing one of these at task entry
# means a run is already in flight, so a fresh delivery is a duplicate (issue #295).
_IN_PROGRESS_STATUSES = frozenset(
    {"extracting", "generating", "synthesizing", "uploading", "composing", "distributing"}
)


def _load_generation_status(episode_id: str) -> Optional[str]:
    """Read an episode's current generation_status. Returns None on missing row or
    DB error so the idempotency guard fails open (proceeds) rather than wedging."""
    try:
        with SyncSessionLocal() as db:
            episode = db.get(Episode, uuid_module.UUID(episode_id))
            return episode.generation_status if episode is not None else None
    except Exception as exc:  # noqa: BLE001 — the idempotency guard must fail open: an unreadable status of any cause means 'proceed' rather than wedging the episode
        logger.warning(
            "Could not read generation_status for episode %s; proceeding: %s",
            episode_id, exc,
        )
        return None


def _skipped_result(reason: str) -> Dict[str, Any]:
    """Result for an idempotency short-circuit — no paid work was run (issue #295)."""
    return {
        "status": "skipped",
        "skipped": True,
        "reason": reason,
        "audio_file_path": None,
        "transcript_path": None,
        "duration_seconds": 0,
        "file_size_bytes": 0,
        "error": None,
    }


def build_podcast_s3_key(user_id: str, episode_id: str) -> str:
    """Canonical S3 key for a generated episode's audio.

    Single source of truth for the key layout so every upload path namespaces
    the object under the user's tenant prefix (``podcasts/user-*/``), which
    bucket-policy/IAM/lifecycle rules scope on (issue #215).
    """
    return f"podcasts/user-{user_id}/episode-{episode_id}.mp3"


def _persist_local_audio(audio_file_path: str, episode_id: str) -> str:
    """Copy generated audio out of ephemeral /tmp into persistent local storage.

    Used when AWS_S3_BUCKET is unset: the artifact would otherwise be the only
    copy and would live in /tmp, so the episode is marked complete yet becomes
    permanently undownloadable once /tmp is cleared (issue #292). Returns the
    persistent path (or the original path unchanged if it is already inside the
    storage dir).

    ``episode_id`` is joined into a real filesystem path, where ``..`` is
    honoured and an absolute component replaces the storage root, so anything
    but a UUID is refused before the filesystem is touched (#575).
    """
    episode_id = str(episode_id)  # join exactly the string that was validated
    if not validate_uuid(episode_id):
        raise ValueError(f"episode_id is not a valid UUID: {episode_id!r}")
    storage_dir = settings.LOCAL_AUDIO_STORAGE_PATH
    os.makedirs(storage_dir, exist_ok=True)
    dest = os.path.join(storage_dir, f"episode-{episode_id}.mp3")
    if os.path.abspath(dest) == os.path.abspath(audio_file_path):
        return audio_file_path
    if os.path.isfile(dest) and not os.path.isfile(audio_file_path):
        # A finalize retry after the temp source was already cleaned up (issue
        # #309): the persistent copy exists, so reuse it instead of failing.
        return dest
    shutil.copy2(audio_file_path, dest)
    return dest


# Snippet types composed before the generated audio; everything else follows it.
_PRE_MAIN_SNIPPET_TYPES = frozenset({"intro", "music"})


def resolve_composition_timeline(
    project_id: Optional[Any],
    audio_file_path: str,
) -> List[Dict[str, Any]]:
    """Build the merge timeline for audio composition (issue #313).

    The router never supplies ``composition_timeline`` (the generated file's
    path doesn't exist at dispatch time), so it is resolved here: the project's
    reusable snippets ordered intro/music → generated audio (``main_content``)
    → outro/midroll/ad/other; within each group snippets play in creation
    order. The generated segment is always included, so the returned timeline
    is never empty. Any snippet-lookup failure degrades to a main-only
    timeline rather than failing composition.
    """
    main_segment = {"file_path": audio_file_path, "segment_type": "main_content"}
    if project_id is None:
        return [main_segment]

    pre: List[Dict[str, Any]] = []
    post: List[Dict[str, Any]] = []
    try:
        with SyncSessionLocal() as db:
            snippets = (
                db.execute(
                    select(AudioSnippet)
                    .where(AudioSnippet.project_id == project_id)
                    .order_by(AudioSnippet.created_at)
                )
                .scalars()
                .all()
            )
            for snippet in snippets:
                # AudioSnippet.file_path holds the S3 key when S3 is configured,
                # so the file usually doesn't exist on this worker's disk.
                if snippet.file_path and os.path.isfile(snippet.file_path):
                    entry = {
                        "file_path": snippet.file_path,
                        "segment_type": snippet.snippet_type,
                    }
                elif snippet.s3_key and settings.AWS_S3_BUCKET:
                    # S3-backed snippet: merge_audio_snippets_task downloads it
                    # to a worker tempfile before merging (issue #376).
                    entry = {
                        "s3_key": snippet.s3_key,
                        "segment_type": snippet.snippet_type,
                    }
                else:
                    logger.warning(
                        "Composition: skipping snippet %s (%s) — no local file "
                        "%r and no downloadable S3 object",
                        snippet.id, snippet.snippet_type, snippet.file_path,
                    )
                    continue
                if snippet.snippet_type in _PRE_MAIN_SNIPPET_TYPES:
                    pre.append(entry)
                else:
                    post.append(entry)
            if snippets and not pre and not post:
                logger.warning(
                    "Composition: project %s has %d snippet(s) but none are "
                    "usable (no local file or S3 object) — composing the "
                    "generated audio only",
                    project_id, len(snippets),
                )
    except Exception as exc:  # noqa: BLE001 — timeline resolution is an enhancement; any failure must fall back to composing the generated audio alone rather than lose the episode
        logger.error(
            "Composition timeline resolution failed for project %s; composing "
            "the generated audio only: %s",
            project_id, exc,
        )
        return [main_segment]

    return pre + [main_segment] + post


def _upload_to_s3_with_retries(
    file_path: str,
    s3_key: str,
    bucket_name: str,
    content_type: str = "audio/mpeg",
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Upload to S3 with explicit retries + exponential backoff.

    ``finalize_episode_generation_task`` calls ``upload_to_s3_task`` synchronously
    (as a plain function, not via Celery), so the task's own ``self.retry`` is
    bypassed — a transient S3 error would propagate raw on the first try
    (issue #220). This wrapper restores retry behaviour for the inline path: it
    retries on a raised exception OR a returned ``{"status": "failed"}`` result,
    sleeping ``calculate_backoff()`` seconds between attempts. Returns the final
    upload result dict (success or failed) without raising.
    """
    last_error = "S3 upload failed"
    for attempt in range(max_attempts):
        try:
            result = upload_to_s3_task(
                file_path=file_path,
                s3_key=s3_key,
                bucket_name=bucket_name,
                content_type=content_type,
            )
            if result.get("status") == "success":
                return result
            last_error = result.get("error") or last_error
            logger.warning(
                f"S3 upload attempt {attempt + 1}/{max_attempts} failed: {last_error}"
            )
        except Exception as exc:  # noqa: BLE001 — this is one attempt inside a bounded retry loop, so every failure must be recorded as last_error and let the loop decide, not escape mid-loop
            last_error = str(exc)
            logger.warning(
                f"S3 upload attempt {attempt + 1}/{max_attempts} raised: {exc}"
            )
        if attempt < max_attempts - 1:
            time.sleep(calculate_backoff(attempt))

    return {
        "status": "failed",
        "s3_key": None,
        "s3_url": None,
        "file_size_bytes": 0,
        "error": last_error,
    }


def _report_progress(task: Task, episode_id: str, stage: str, progress: int, status: str) -> None:
    task.update_state(
        state='PROGRESS',
        meta={
            'episode_id': episode_id,
            'stage': stage,
            'progress': progress,
            'status': status,
        }
    )


def _claim_generation(episode_id: str, task_id: str, retries: Optional[int]) -> Optional[Dict[str, Any]]:
    """Return a skipped result for a duplicate delivery, else take the run lock.

    Idempotency guard (issue #295): short-circuit before any paid work so a
    broker-redelivered duplicate or double-dispatch cannot re-run the paid
    LLM/TTS pipeline. A genuine retry (same task_id) is allowed through.
    """
    is_retry = bool(retries)  # Celery's request.retries: None or a non-negative count
    status = _load_generation_status(episode_id)
    if status == "complete":
        logger.info("Episode %s already complete; skipping duplicate generation", episode_id)
        return _skipped_result("already complete")
    if status in _IN_PROGRESS_STATUSES and not is_retry:
        logger.warning(
            "Episode %s already in progress (status=%s); skipping duplicate run",
            episode_id, status,
        )
        return _skipped_result(f"already in progress ({status})")
    if not acquire_generation_lock(episode_id, task_id):
        logger.warning(
            "Episode %s generation lock held by another run; skipping concurrent duplicate",
            episode_id,
        )
        return _skipped_result("concurrent run in progress")
    return None


# Voices for an episode with no TTS configuration: the defaults the previous
# engine used, kept so unconfigured episodes sound the same across the #543
# cut-over. The model is the engine's verified default (ENGINE_OPENAI_TTS_MODEL).
_DEFAULT_TTS_CONFIG = {"voice_1": "echo", "voice_2": "shimmer"}


def _effective_tts(episode: Episode):
    """The episode's TTS configuration, else its project's default (#217)."""
    if episode.tts_config is not None:
        return episode.tts_config
    return episode.project.default_tts_config if episode.project else None


def _load_native_inputs(episode_id: str) -> tuple:
    """Return ``(user_id, tts_provider, tts_config)`` for the native engine.

    Read from the episode row, the one source of truth for the configuration,
    rather than from the router's kwargs. An episode with no TTS configuration
    gets _DEFAULT_TTS_CONFIG.
    """
    with SyncSessionLocal() as db:
        episode = db.get(Episode, uuid_module.UUID(episode_id))
        if episode is None or episode.user_id is None:
            raise EngineError(f"Episode {episode_id} has no owner to store its transcript under")
        tts = _effective_tts(episode)
        if tts is None:
            return str(episode.user_id), "openai", dict(_DEFAULT_TTS_CONFIG)
        return str(episode.user_id), tts.provider, dict(tts.config or {})


def _collect_sources(text_content: Optional[str], urls: Optional[List[str]]) -> List[str]:
    """The engine's text inputs: extracted/pasted text, then pending URLs.

    Pending URLs go through the same SSRF-guarded fetch as extraction
    (#206, #543): the engine takes text, not URLs.
    """
    sources = [text_content] if text_content else []
    if urls:
        extractor = ContentExtractionService()
        sources += [extractor.fetch_url_text(url) for url in urls]
    return sources


def _run_native_engine(
    task: Task,
    episode_id: str,
    run_dir: str,
    *,
    urls: Optional[List[str]],
    text_content: Optional[str],
    image_paths: Optional[List[str]],
    topic: Optional[str],
    conversation_config: Optional[Dict[str, Any]],
    longform: bool,
) -> tuple:
    """Script, voice and store an episode with the in-repo engine (#543)."""
    if image_paths or topic:
        # No source type produces either today (see test_dependency_reachability);
        # refuse rather than silently generate without them.
        raise EngineError("Image and topic sources are not supported by the engine")
    user_id, tts_provider, tts_config = _load_native_inputs(episode_id)
    # Resolved before any paid call, so a misconfigured episode fails for free.
    VoiceConfig.from_tts_config(tts_config, provider=tts_provider)

    script, sources = _paid_script(
        task, episode_id, text_content, urls, conversation_config, longform
    )
    _record_screening(episode_id, script, sources)
    _record_quality_metrics(episode_id, script)

    # Stage 3: Audio Synthesis (66-100%)
    _report_progress(task, episode_id, 'audio', 66, 'Synthesizing audio...')
    audio_path = synthesise(tts_provider, script, tts_config, Path(run_dir))
    transcript_path = persist_transcript(script, user_id, episode_id)
    # Recorded on the row immediately, not left for finalize: if the episode is
    # deleted while generation is still running, or finalize fails for good,
    # the delete flows can only queue a transcript the row already names.
    _update_episode(episode_id, {"transcript_path": transcript_path})
    return str(audio_path), transcript_path


def _paid_script(task: Task, episode_id: str, text_content, urls, conversation_config, longform: bool):
    """The script and the sources it was written from, bought once per generation (#620).

    A failure after scripting (TTS, transcript storage, a screening write)
    retries the whole task under the same task id; the retry reuses both
    instead of fetching the URLs and paying for the script again, and so
    screens the script against the text it was written from. A direct call has
    no task id, so nothing to key on and nothing to reuse.
    """
    task_id = task.request.id
    cached = load_run(task_id) if task_id else None
    if cached is not None:
        logger.info("Task %s: reusing the script bought by an earlier attempt", task_id)
        return cached
    sources = _collect_sources(text_content, urls)
    _report_progress(task, episode_id, 'extraction', 33, 'Content extracted successfully')

    # Stage 2: Transcript Generation (33-66%), reported per long-form part.
    def on_progress(stage: str, percent: int) -> None:
        _report_progress(
            task, episode_id, 'transcript', 33 + round(percent * 33 / 100),
            'Generating podcast transcript...',
        )

    _report_progress(task, episode_id, 'transcript', 33, 'Generating podcast transcript...')
    script = generate_script(
        sources, conversation_config, longform=longform, on_progress=on_progress
    )
    if task_id:
        # Outlives every attempt this generation can make, then expires.
        ttl = (task.max_retries + 1) * (settings.CELERY_TASK_TIME_LIMIT + 60)
        save_run(task_id, script, sources, ttl_seconds=ttl)
    return script, sources


def _measure_audio(audio_file_path: str) -> tuple:
    """Return ``(file_size_bytes, duration_seconds)`` for the generated file."""
    file_size_bytes = os.path.getsize(audio_file_path)
    audio = AudioSegment.from_file(audio_file_path)
    return file_size_bytes, len(audio) / 1000.0


def _record_quality_metrics(episode_id: str, script) -> None:
    """Store the script's quality metrics for the read endpoints (#570).

    Best effort: unlike screening, a lost write only leaves the metrics endpoint
    answering 204, so it never fails a run whose script is already paid for.
    """
    recorded = _update_episode(
        episode_id,
        {},
        progress_updates={"quality_metrics": quality_metrics(script), "calculated_at": _utcnow_iso()},
    )
    if not recorded:
        logger.warning("Episode %s: quality metrics were not recorded", episode_id)


def _record_screening(episode_id: str, script, sources: List[str]) -> None:
    """Record what screening found, clearing any earlier result (#576).

    Written for clean scripts too: a regeneration that comes back clean must
    release a hold left by an earlier, flagged run.
    """
    flags = screen_script(script, sources)
    recorded = _update_episode(
        episode_id,
        {},
        progress_updates={
            "content_flags": flags,
            "content_review": "pending" if flags else None,
        },
    )
    if not recorded:
        # _update_episode swallows DB errors. Fail closed: an unrecorded flag
        # would let the episode publish unheld. The task retries the run.
        raise EngineError(f"Episode {episode_id}: could not record content screening")


def _distribution_allowed(episode_id: str, enable_distribution: bool) -> bool:
    """Platform distribution, unless screening is holding the episode (#576)."""
    if enable_distribution and episode_held_for_review(episode_id):
        logger.warning(
            "Episode %s: platform distribution held until its content flags are reviewed",
            episode_id,
        )
        return False
    return enable_distribution


def _dispatch_downstream(
    episode_id: str,
    generation_result: Dict[str, Any],
    *,
    enable_composition: bool,
    composition_timeline: Optional[List[Dict[str, Any]]],
    enable_distribution: bool,
    platforms: Optional[Dict[str, Dict[str, Any]]],
) -> None:
    """Hand a successful generation to the workflow chain or to finalization."""
    enable_distribution = _distribution_allowed(episode_id, enable_distribution)
    # Determine whether to use the enhanced workflow chain
    # (composition/distribution) or the simpler finalization task.
    use_workflow_chain = enable_composition or (
        enable_distribution and bool(platforms)
    )
    if use_workflow_chain:
        _dispatch_workflow_chain(
            episode_id, generation_result,
            enable_composition=enable_composition,
            composition_timeline=composition_timeline,
            enable_distribution=enable_distribution,
            platforms=platforms,
        )
    else:
        _finalize_or_fall_back(episode_id, generation_result)


def _persist_generation_metadata(episode_id: str, generation_result: Dict[str, Any]) -> tuple:
    """Write file metadata before the chain runs; return ``(user_id, project_id)``.

    The chain's callbacks only write S3 fields/status, so without this any
    episode generated with composition or distribution would lose
    file_path/transcript_path/duration_seconds/file_size_bytes that the default
    finalize path records (issue #211).
    """
    user_id: Optional[str] = None
    project_id = None
    try:
        with SyncSessionLocal() as db:
            episode = db.get(Episode, uuid_module.UUID(episode_id))
            if episode is not None:
                project_id = episode.project_id
            if episode is not None and episode.user_id is not None:
                user_id = str(episode.user_id)
                episode.file_path = generation_result["audio_file_path"]
                episode.transcript_path = generation_result.get("transcript_path")
                episode.duration_seconds = generation_result["duration_seconds"]
                episode.file_size_bytes = generation_result["file_size_bytes"]
                db.commit()
    except Exception as persist_err:  # noqa: BLE001 — the audio is already generated; failing to persist its metadata must not abort the workflow dispatch that follows
        logger.error(
            "Episode %s: failed to persist generation metadata before "
            "workflow dispatch: %s",
            episode_id, persist_err,
        )
    return user_id, project_id


def _timeline_for(
    enable_composition: bool,
    composition_timeline: Optional[List[Dict[str, Any]]],
    project_id,
    audio_file_path: str,
) -> Optional[List[Dict[str, Any]]]:
    # The router never supplies a timeline (the generated file's path
    # doesn't exist at dispatch time), so resolve it here; a caller-
    # supplied timeline wins (issue #313).
    if enable_composition and not composition_timeline:
        return resolve_composition_timeline(project_id, audio_file_path)
    return composition_timeline


def _dispatch_workflow_chain(
    episode_id: str,
    generation_result: Dict[str, Any],
    *,
    enable_composition: bool,
    composition_timeline: Optional[List[Dict[str, Any]]],
    enable_distribution: bool,
    platforms: Optional[Dict[str, Dict[str, Any]]],
) -> None:
    audio_file_path = generation_result["audio_file_path"]
    user_id, project_id = _persist_generation_metadata(episode_id, generation_result)

    # Fail closed: without a resolved user_id the upload chain would write
    # a non-tenant-scoped key (podcasts/user-/episode-…), the exact layout
    # bug this path is meant to prevent (issue #215). Skip dispatch rather
    # than orphan an object outside podcasts/user-*/.
    if not user_id:
        logger.critical(
            "Episode %s: workflow dispatch skipped — user_id could not be "
            "resolved, refusing to upload outside the tenant prefix",
            episode_id,
        )
        return

    composition_timeline = _timeline_for(
        enable_composition, composition_timeline, project_id, audio_file_path
    )

    # Trigger the full workflow: S3 upload → [composition] → [distribution]
    # Isolated try/except so a broker hiccup cannot mark a successful
    # generation as "failed" or orphan the audio file.
    logger.info(
        "Episode %s: triggering workflow chain "
        "(composition=%s, distribution=%s, platforms=%s)",
        episode_id, enable_composition, enable_distribution,
        list(platforms or {}),
    )
    try:
        build_generation_workflow(
            episode_id=episode_id,
            audio_file_path=audio_file_path,
            user_id=user_id,
            s3_bucket=settings.AWS_S3_BUCKET,
            enable_composition=enable_composition,
            composition_timeline=composition_timeline,
            enable_distribution=enable_distribution,
            platforms=platforms,
        ).apply_async()
    except Exception as broker_err:  # noqa: BLE001 — generation already succeeded, so a broker failure of any kind must be recorded loudly and never re-mark a successful run as failed
        logger.critical(
            "Celery broker unavailable after successful generation for "
            "episode %s — workflow chain could not be dispatched: %s",
            episode_id, broker_err,
        )


def _finalize_or_fall_back(episode_id: str, generation_result: Dict[str, Any]) -> None:
    # Default path: simple S3 upload + DB update via finalization task.
    # Isolated try/except: a broker hiccup must not mark a successful
    # generation as "failed" or orphan the audio file.
    try:
        finalize_episode_generation_task.delay(
            episode_id=episode_id,
            generation_result=generation_result,
        )
    except Exception as broker_err:  # noqa: BLE001 — a broker hiccup must not orphan a successful generation, so any dispatch failure falls through to the synchronous finalization below
        logger.critical(
            "Celery broker unavailable after successful generation for "
            "episode %s — falling back to synchronous finalization: %s",
            episode_id, broker_err,
        )
        try:
            finalize_episode_generation_task(
                episode_id=episode_id,
                generation_result=generation_result,
            )
        except Exception as sync_err:  # noqa: BLE001 — this is the fallback's fallback: the synchronous path has failed too, so there is nothing left to try and the only correct action is to record it
            logger.critical(
                "Synchronous finalization also failed for episode %s: %s",
                episode_id, sync_err,
            )


def _fail_on_soft_timeout(
    task: Task, episode_id: str, task_id: str, run_dir: Optional[str], lock_held: bool
) -> Dict[str, Any]:
    # Hit the soft time limit (e.g. a long-form run exceeding the ceiling).
    # SoftTimeLimitExceeded subclasses BaseException, so it bypasses the broad
    # `except Exception` handler; the task catches it explicitly and treats it
    # as terminal — retrying would just hit the limit again. Persist 'failed' to
    # the DB so the episode does not stay stuck at 'queued' (issue #294).
    msg = "Generation exceeded the soft time limit"
    logger.error("Podcast generation soft-timeout for episode %s", episode_id)
    if run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)
    _update_episode(
        episode_id,
        updates={"generation_status": "failed"},
        progress_updates={
            "status": "failed",
            "error_message": msg,
            "failed_at": _utcnow_iso(),
        },
    )
    task.update_state(
        state='FAILURE',
        meta={
            'episode_id': episode_id,
            'stage': 'failed',
            'progress': 0,
            'status': f'Generation failed: {msg}',
        },
    )
    if lock_held:
        release_generation_lock(episode_id, task_id)
    return {
        "status": "failed",
        "audio_file_path": None,
        "transcript_path": None,
        "duration_seconds": 0,
        "file_size_bytes": 0,
        "error": msg,
    }


def _retry_or_fail(
    task: Task, e: Exception, episode_id: str, task_id: str,
    run_dir: Optional[str], lock_held: bool,
) -> None:
    """Retry the task, or record the permanent failure; always raises."""
    logger.warning(
        f"Podcast generation error for episode {episode_id}, "
        f"attempt {task.request.retries + 1}/{task.max_retries + 1}: {e}"
    )
    # Each attempt creates its own run dir (a retry re-executes the whole
    # task body), so this attempt's partial artifacts are dead weight (#309).
    if run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)
    # Celery re-raises the original exception when retry(exc=...) is out of
    # attempts, so the `except MaxRetriesExceededError` this replaces never
    # ran: the #294 status write and the lock release were stranded, and every
    # exhausted generation leaked its Redis lock until TTL (#520). Raising is
    # what records FAILURE and fires the router's link_error.
    if task.request.retries >= task.max_retries:
        logger.error(
            f"Podcast generation failed after {task.max_retries} retries "
            f"for episode {episode_id}: {e}"
        )
        # Persist 'failed' to the DB; the result backend alone would leave the
        # episode stuck at 'queued' (issue #294).
        _update_episode(
            episode_id,
            updates={"generation_status": "failed"},
            progress_updates={
                "status": "failed",
                "error_message": f"Generation failed after retries: {e}",
                "failed_at": _utcnow_iso(),
            },
        )
        if lock_held:
            release_generation_lock(episode_id, task_id)
        raise e
    _report_progress(task, episode_id, 'retrying', 0, f'Retrying after error: {str(e)}')
    raise task.retry(exc=e, countdown=calculate_backoff(task.request.retries))


@celery_app.task(
    bind=True,
    name="generate_podcast",
    time_limit=settings.CELERY_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    max_retries=3,
    # Fail-fast override of the global at-least-once settings (worker.py:47-48):
    # this task runs paid, non-idempotent LLM/TTS work, so a crashed worker must
    # NOT re-queue and re-run it. Abrupt loss surfaces as a failed/stuck episode
    # (handled by the #294 reaper) instead of duplicate billing (issue #295).
    acks_late=False,
    reject_on_worker_lost=False,
)
def generate_podcast_task(
    self: Task,
    episode_id: str,
    urls: Optional[List[str]] = None,
    text_content: Optional[str] = None,
    image_paths: Optional[List[str]] = None,
    topic: Optional[str] = None,
    tts_model: str = "openai",
    conversation_config: Optional[Dict[str, Any]] = None,
    longform: bool = False,
    enable_composition: bool = False,
    composition_timeline: Optional[List[Dict[str, Any]]] = None,
    enable_distribution: bool = False,
    platforms: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Generate a podcast episode with the in-repo engine (src/engine): script,
    voice, store the transcript, and report progress for the GUI.

    After successful generation, optionally triggers downstream workflow steps:
    - S3 upload (always, via finalize_episode_generation_task or build_generation_workflow)
    - Audio composition (if enable_composition=True)
    - Platform distribution (if enable_distribution=True and platforms provided)

    Args:
        self: Celery task instance (for progress updates)
        episode_id: UUID of the episode being generated
        urls: List of URLs to extract content from (regular + YouTube URLs)
        text_content: Raw text content (also carries pre-extracted file/PDF content)
        image_paths: List of image file paths
        topic: Topic for content generation (uses web search)
        tts_model: Accepted and ignored: the router still sends it (#623). The
            engine reads the episode's stored TTS configuration itself
        conversation_config: Custom conversation configuration
        longform: Whether to generate long-form content
        enable_composition: Whether to merge audio snippets after generation
        composition_timeline: Timeline segments for audio composition
        enable_distribution: Whether to distribute to platforms after generation
        platforms: Platform name → config dict for distribution

    Returns:
        Dictionary with generation results:
        {
            "status": "success" | "failed",
            "audio_file_path": str,
            "transcript_path": Optional[str],  # S3 key or local path of the stored transcript
            "duration_seconds": float,
            "file_size_bytes": int,
            "error": Optional[str]
        }
    """
    task_id = self.request.id or "unknown"
    lock_held = False
    run_dir: Optional[str] = None

    try:
        skipped = _claim_generation(episode_id, task_id, self.request.retries)
        if skipped is not None:
            return skipped
        lock_held = True

        # Record in-progress state so subsequent deliveries observe in-flight work
        # and the status no longer jumps straight from 'queued' to a terminal value.
        _update_episode(episode_id, {"generation_status": "generating"})

        # Stage 1: Content Extraction (0-33%)
        _report_progress(self, episode_id, 'extraction', 0, 'Extracting content from sources...')

        run_dir = tempfile.mkdtemp(prefix=GENERATION_RUN_DIR_PREFIX)
        audio_file_path, transcript_path = _run_native_engine(
            self, episode_id, run_dir,
            urls=urls, text_content=text_content, image_paths=image_paths,
            topic=topic, conversation_config=conversation_config, longform=longform,
        )
        file_size_bytes, duration_seconds = _measure_audio(audio_file_path)

        # Completion
        _report_progress(self, episode_id, 'complete', 100, 'Podcast generated successfully')

        generation_result = {
            "status": "success",
            "audio_file_path": audio_file_path,
            # The engine's persisted transcript: S3 key or local path (#543).
            "transcript_path": transcript_path,
            "duration_seconds": duration_seconds,
            "file_size_bytes": file_size_bytes,
            "error": None
        }

        _dispatch_downstream(
            episode_id, generation_result,
            enable_composition=enable_composition,
            composition_timeline=composition_timeline,
            enable_distribution=enable_distribution,
            platforms=platforms,
        )
        release_generation_lock(episode_id, task_id)
        return generation_result

    except SoftTimeLimitExceeded:
        return _fail_on_soft_timeout(self, episode_id, task_id, run_dir, lock_held)

    except Exception as e:  # noqa: BLE001 — this is the task's retry classification point; every failure must resolve to retry-or-permanent-failed so the episode never stays 'queued'
        _retry_or_fail(self, e, episode_id, task_id, run_dir, lock_held)


@celery_app.task(
    bind=True,
    # Also run in-process by _finalize_or_fall_back during a broker outage, where
    # a progress write has no id and no backend to land in (#633).
    base=BestEffortProgressTask,
    name="finalize_episode_generation",
    time_limit=settings.CELERY_TASK_TIME_LIMIT,
    soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    max_retries=3,
)
def finalize_episode_generation_task(
    self: Task,
    episode_id: str,
    generation_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Post-generation callback: upload audio to S3 and update Episode in DB.

    This task runs after generate_podcast_task completes. It:
    1. Uploads the generated audio file to S3 (if AWS_S3_BUCKET is configured)
    2. Updates Episode.s3_url, s3_key, file_path, duration_seconds, file_size_bytes
    3. Sets Episode.generation_status to "complete"

    If AWS_S3_BUCKET is not configured, the episode is marked complete without S3 upload.
    If S3 upload fails, the episode is marked failed with an error message.

    Args:
        self: Celery task instance
        episode_id: UUID of the episode being finalized
        generation_result: Result dict from generate_podcast_task

    Returns:
        Dictionary with finalization results
    """
    logger.info(f"Finalizing episode {episode_id} after generation")

    # Open a synchronous database session (Celery cannot use async sessions)
    with SyncSessionLocal() as db:
        try:
            episode = db.get(Episode, uuid_module.UUID(episode_id))
            if episode is None:
                logger.error(f"Episode {episode_id} not found in database")
                return {"status": "failed", "error": f"Episode {episode_id} not found"}

            # If generation itself failed, mark episode as failed
            if generation_result.get("status") != "success":
                error_msg = generation_result.get("error", "Unknown generation error")
                episode.generation_status = "failed"
                episode.generation_progress = {
                    **dict(episode.generation_progress or {}),
                    "stage": "failed",
                    "error_message": error_msg,
                }
                db.commit()
                return {"status": "failed", "error": error_msg}

            audio_file_path = generation_result["audio_file_path"]
            duration_seconds = generation_result.get("duration_seconds", 0)
            file_size_bytes = generation_result.get("file_size_bytes", 0)

            # Always store local file path
            episode.file_path = audio_file_path
            episode.transcript_path = generation_result.get("transcript_path")
            episode.duration_seconds = duration_seconds
            episode.file_size_bytes = file_size_bytes

            s3_url = None
            s3_key = None
            # Captured now so the absorb branch below can use them without
            # depending on the `episode` ORM object, which is expired (and its
            # row gone) after the rollback there (issue #366).
            finalized_local_path = None
            episode_tenant_id = episode.tenant_id

            # S3 upload (skip gracefully if bucket not configured)
            if settings.AWS_S3_BUCKET:
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'episode_id': episode_id,
                        'stage': 'uploading',
                        'progress': 0,
                        'status': 'Uploading to S3...'
                    }
                )

                # Update episode status to 'uploading'
                episode.generation_status = "uploading"
                episode.generation_progress = {
                    **dict(episode.generation_progress or {}),
                    "stage": "uploading",
                    "progress": 0,
                    "status": "Uploading to S3...",
                }
                db.commit()

                # Build S3 key using the canonical helper (issue #215)
                s3_key = build_podcast_s3_key(str(episode.user_id), episode_id)

                upload_result = _upload_to_s3_with_retries(
                    file_path=audio_file_path,
                    s3_key=s3_key,
                    bucket_name=settings.AWS_S3_BUCKET,
                    content_type="audio/mpeg",
                )

                if upload_result["status"] == "success":
                    s3_url = upload_result["s3_url"]
                    s3_key = upload_result["s3_key"]
                    logger.info(f"Successfully uploaded episode {episode_id} to S3: {s3_url}")
                else:
                    error_msg = upload_result.get("error", "S3 upload failed")
                    logger.error(f"S3 upload failed for episode {episode_id}: {error_msg}")
                    episode.generation_status = "failed"
                    episode.generation_progress = {
                        **dict(episode.generation_progress or {}),
                        "stage": "failed",
                        "error_message": f"S3 upload failed: {error_msg}",
                    }
                    db.commit()
                    return {"status": "failed", "error": error_msg}
            else:
                # No S3: persist the artifact off ephemeral /tmp so the episode
                # stays downloadable from local disk (issue #292), then drop the
                # per-run temp dir now that a persistent copy exists (issue #309).
                persistent_path = _persist_local_audio(audio_file_path, episode_id)
                episode.file_path = persistent_path
                finalized_local_path = persistent_path
                _cleanup_temp_file(audio_file_path)
                logger.info(
                    f"AWS_S3_BUCKET not configured; persisted episode {episode_id} "
                    f"audio to {persistent_path}"
                )

            # Update episode with all file metadata and mark as complete
            episode.s3_url = s3_url
            episode.s3_key = s3_key
            episode.generation_status = "complete"
            episode.generation_progress = {
                **dict(episode.generation_progress or {}),
                "stage": "complete",
                "progress": 100,
                "status": "Generation complete",
            }
            try:
                db.commit()
            except StaleDataError:
                # The episode row was deleted by another transaction between the
                # unlocked fetch above and this commit (issue #366) — the ORM's
                # 0-row-matched UPDATE raises here even without a version_id_col.
                # The audio is already durably uploaded/persisted with nothing
                # left to reference it, so it must be queued for deletion instead
                # of silently orphaned (IAM has no s3:ListBucket to find it later).
                db.rollback()
                still_present = db.get(Episode, uuid_module.UUID(episode_id)) is not None
                if still_present:
                    # Not the delete race this handles — fail cleanly rather than
                    # guess at what else could cause a 0-row-matched UPDATE.
                    logger.error(
                        f"Episode {episode_id} commit reported stale data, but the "
                        "row is still present; not absorbing"
                    )
                    return {"status": "failed", "error": "Stale data on episode commit"}

                logger.warning(
                    f"Episode {episode_id} was deleted mid-finalization; queuing "
                    f"{'s3_key=' + s3_key if s3_key else 'file_path=' + str(finalized_local_path)} "
                    "for deletion instead of orphaning it"
                )
                # s3_key and finalized_local_path are mutually exclusive by
                # construction (only one of the two branches above runs).
                _queue_orphaned_storage(
                    s3_key=s3_key,
                    file_path=finalized_local_path,
                    tenant_id=episode_tenant_id,
                )
                return {
                    "status": "absorbed",
                    "episode_id": episode_id,
                    "s3_key": s3_key,
                    "file_path": finalized_local_path,
                }

            logger.info(f"Episode {episode_id} finalized successfully")

            # The feed on S3 predates this episode; refresh it so RSS-model
            # platforms (Spotify/Apple) pick the episode up (issue #382).
            # Best-effort, and guarded locally: the surrounding except calls
            # self.retry, and a feed problem must never re-run finalization
            # of an already-committed completion.
            try:
                refresh_project_rss_feed(episode.project_id, episode.user_id)
            except Exception as rss_exc:  # noqa: BLE001 — the completion is already committed, so an RSS refresh failure of any kind must be logged and dropped rather than re-run finalization (#382)
                logger.error(
                    f"RSS refresh after finalizing episode {episode_id} failed: {rss_exc}"
                )

            return {
                "status": "success",
                "episode_id": episode_id,
                "s3_url": s3_url,
                "s3_key": s3_key,
                "file_path": audio_file_path,
                "duration_seconds": duration_seconds,
                "file_size_bytes": file_size_bytes,
            }

        except Exception as e:  # noqa: BLE001 — finalization's retry classification point: any failure must become a retry or a recorded permanent failure, never an unacked task
            logger.warning(
                f"Finalization error for episode {episode_id}, "
                f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
            )
            # Celery re-raises the original exception on exhaustion, so the
            # `except MaxRetriesExceededError` this replaces never ran and the
            # #311 status write was stranded. Finalize is dispatched with no
            # link_error, so without this write an exhausted finalize left the
            # episode in-progress forever (#520).
            if self.request.retries >= self.max_retries:
                logger.error(
                    f"Finalization failed after {self.max_retries} retries "
                    f"for episode {episode_id}: {e}"
                )
                # The triggering error may have left the session in a failed-
                # transaction state; reset it so the 'failed' status write
                # below can actually persist (issue #311).
                try:
                    db.rollback()
                except Exception as rollback_err:  # noqa: BLE001 — the session may already be in a failed-transaction state, and a rollback failure must not stop the failure-status write below from being attempted (#311)
                    logger.error(
                        "Rollback before failure-status write failed for "
                        f"episode {episode_id}: {rollback_err}"
                    )
                try:
                    episode = db.get(Episode, uuid_module.UUID(episode_id))
                    if episode:
                        episode.generation_status = "failed"
                        episode.generation_progress = {
                            **dict(episode.generation_progress or {}),
                            "stage": "failed",
                            "error_message": f"Finalization error: {str(e)}",
                        }
                        db.commit()
                except Exception as db_err:  # noqa: BLE001 — this is the last-resort status write; if the DB is unreachable the original error must still propagate rather than be masked by the cleanup's
                    logger.error(f"Failed to update episode status after error: {db_err}")
                raise
            raise self.retry(exc=e, countdown=calculate_backoff(self.request.retries))


def build_generation_workflow(
	episode_id: str,
	audio_file_path: str,
	user_id: str,
	s3_bucket: Optional[str] = None,
	enable_composition: bool = False,
	composition_timeline: Optional[List[Dict[str, Any]]] = None,
	output_path: Optional[str] = None,
	enable_distribution: bool = False,
	platforms: Optional[Dict[str, Dict[str, Any]]] = None,
) -> chain:
	"""
	Build a Celery workflow chain that uploads, optionally composes, and
	optionally distributes a generated podcast episode, with success and error
	callbacks updating the Episode record at each stage.

	Args:
		episode_id: UUID string of the episode.
		audio_file_path: Local path to the generated audio file.
		user_id: UUID string of the owning user, for the canonical S3 key prefix.
		s3_bucket: S3 bucket name for upload.  Defaults to settings.AWS_S3_BUCKET.
		enable_composition: Whether to include the audio-composition step.
		composition_timeline: Timeline segments for merge_audio_snippets_task.
		output_path: Output path for the composed audio file.
		enable_distribution: Whether to include platform-distribution steps.
		platforms: Mapping of platform_name → config dict for distribution.

	Returns:
		A Celery ``chain`` object ready to be called with ``.apply_async()``.
	"""
	from src.tasks.callbacks import (
		on_composition_complete,
		on_distribution_complete,
		on_upload_complete,
		on_workflow_complete,
		on_workflow_failure,
	)
	from src.tasks.audio_composition import merge_audio_snippets_task
	from src.tasks.platform_distribution import distribute_to_platform_task

	bucket = s3_bucket or settings.AWS_S3_BUCKET or ""
	s3_key = build_podcast_s3_key(user_id, episode_id)

	# Chain stages use immutable signatures (.si). In a Celery chain a mutable
	# .s() signature has the *previous* task's return value prepended as the first
	# positional arg; since these stages are called with keyword args (episode_id=…)
	# that would raise "got multiple values for argument 'episode_id'" at runtime.
	# Each stage re-reads the Episode from the DB (state is persisted by the
	# on_*_complete callbacks), so it does not need the prior task's result.

	workflow_tasks = []

	# Composition runs BEFORE upload so the artifact uploaded to S3 — and therefore
	# the one distributed — is the composed file, not the pre-composition audio
	# (issue #211). Without distribution/composition reordering, enabling both would
	# publish the uncomposed audio.
	final_audio_path = audio_file_path

	# Stage: audio composition (optional)
	if enable_composition:
		# Derive from gettempdir(), not a literal /tmp: the cleanup guard in
		# _cleanup_temp_file is scoped to gettempdir(), so a TMPDIR override
		# would otherwise leave every composed file outside its reach (#309).
		composed_output = output_path or os.path.join(
			tempfile.gettempdir(), f"composed_{episode_id}.mp3"
		)
		composition_sig = merge_audio_snippets_task.si(
			episode_id=episode_id,
			timeline=composition_timeline or [],
			output_path=composed_output,
		).set(
			link=on_composition_complete.s(episode_id=episode_id),
			link_error=on_workflow_failure.s(
				episode_id=episode_id, task_name="merge_audio_snippets"
			),
		)
		workflow_tasks.append(composition_sig)
		final_audio_path = composed_output

	# Stage: S3 upload of the final artifact (composed if composition ran). On
	# success on_upload_complete persists Episode.s3_url; distribution gates on that
	# committed s3_url, so a failed upload never results in a published episode.
	upload_sig = upload_to_s3_task.si(
		file_path=final_audio_path,
		s3_key=s3_key,
		bucket_name=bucket,
		content_type="audio/mpeg",
	).set(
		link=on_upload_complete.s(episode_id=episode_id),
		link_error=on_workflow_failure.s(episode_id=episode_id, task_name="upload_to_s3"),
	)
	workflow_tasks.append(upload_sig)

	# Stage: platform distribution (optional). All metadata (title/description/
	# duration/explicit/audio_url) is read from the fresh Episode row inside
	# distribute_to_platform_task, which waits for the committed s3_url (issue #211).
	if enable_distribution and platforms:
		for platform_name, platform_config in platforms.items():
			dist_sig = distribute_to_platform_task.si(
				episode_id=episode_id,
				platform=platform_name,
				platform_config=platform_config,
				episode_metadata={},
			).set(
				link=on_distribution_complete.s(
					episode_id=episode_id, platform=platform_name
				),
				link_error=on_workflow_failure.s(
					episode_id=episode_id,
					task_name=f"distribute_to_platform:{platform_name}",
				),
			)
			workflow_tasks.append(dist_sig)

	# No chain-level link_error: Celery copies it onto every member task, and each
	# stage above already has its own. It fired a second, generic errback that
	# could overwrite the precise failed_task with "workflow" (issue #519).
	workflow = chain(*workflow_tasks)
	workflow.link(on_workflow_complete.s(episode_id=episode_id))

	return workflow
