"""
Celery tasks for podcast generation
Wraps the existing podcastfy CLI functionality
"""
import os
import time
import uuid as uuid_module
import logging
from celery import Task, chain
from typing import Optional, List, Dict, Any
from pydub import AudioSegment

from src.worker import celery_app
from src.config import settings
from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.tasks.s3_upload import upload_to_s3_task
from src.tasks.retry_utils import calculate_backoff

logger = logging.getLogger(__name__)


def build_podcast_s3_key(user_id: str, episode_id: str) -> str:
    """Canonical S3 key for a generated episode's audio.

    Single source of truth for the key layout so every upload path namespaces
    the object under the user's tenant prefix (``podcasts/user-*/``), which
    bucket-policy/IAM/lifecycle rules scope on (issue #215).
    """
    return f"podcasts/user-{user_id}/episode-{episode_id}.mp3"


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
        except Exception as exc:
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


@celery_app.task(bind=True, name="generate_podcast", time_limit=600, max_retries=3)
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
    Generate a podcast episode using the existing Podcastfy CLI.

    This task wraps the existing generate_podcast() function from the CLI
    and provides progress tracking for the GUI.

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
        tts_model: TTS provider (openai, elevenlabs, gemini, etc.)
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
            "transcript_path": str,
            "duration_seconds": float,
            "file_size_bytes": int,
            "error": Optional[str]
        }
    """
    try:
        # Stage 1: Content Extraction (0-33%)
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'extraction',
                'progress': 0,
                'status': 'Extracting content from sources...'
            }
        )

        from podcastfy.client import generate_podcast

        # Update progress after extraction
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'extraction',
                'progress': 33,
                'status': 'Content extracted successfully'
            }
        )

        # Stage 2: Transcript Generation (33-66%)
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'transcript',
                'progress': 33,
                'status': 'Generating podcast transcript...'
            }
        )

        # Generate the podcast using existing CLI.
        # podcastfy 0.4.1 has no `file`/`youtube_urls` kwargs: YouTube URLs flow
        # through `urls`, and file/PDF sources are pre-extracted into `text`.
        result = generate_podcast(
            urls=urls,
            text=text_content,
            image_paths=image_paths,
            topic=topic,
            tts_model=tts_model,
            conversation_config=conversation_config,
            longform=longform,
        )

        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'transcript',
                'progress': 66,
                'status': 'Transcript generated successfully'
            }
        )

        # Stage 3: Audio Synthesis (66-100%)
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'audio',
                'progress': 66,
                'status': 'Synthesizing audio...'
            }
        )

        # Extract file information
        audio_file_path = result
        file_size_bytes = os.path.getsize(audio_file_path)

        # Get audio duration
        audio = AudioSegment.from_file(audio_file_path)
        duration_seconds = len(audio) / 1000.0

        # Completion
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'complete',
                'progress': 100,
                'status': 'Podcast generated successfully'
            }
        )

        generation_result = {
            "status": "success",
            "audio_file_path": audio_file_path,
            "transcript_path": audio_file_path.replace('.mp3', '_transcript.txt'),
            "duration_seconds": duration_seconds,
            "file_size_bytes": file_size_bytes,
            "error": None
        }

        # Determine whether to use the enhanced workflow chain
        # (composition/distribution) or the simpler finalization task.
        use_workflow_chain = enable_composition or (
            enable_distribution and bool(platforms)
        )

        if use_workflow_chain:
            # Persist the generated file metadata before handing off to the
            # workflow chain. The chain's callbacks only write S3 fields/status, so
            # without this any episode generated with composition or distribution
            # would lose file_path/transcript_path/duration_seconds/file_size_bytes
            # that the default finalize path records (issue #211).
            user_id: Optional[str] = None
            try:
                with SyncSessionLocal() as db:
                    episode = db.get(Episode, uuid_module.UUID(episode_id))
                    if episode is not None and episode.user_id is not None:
                        user_id = str(episode.user_id)
                        episode.file_path = audio_file_path
                        episode.transcript_path = generation_result.get("transcript_path")
                        episode.duration_seconds = duration_seconds
                        episode.file_size_bytes = file_size_bytes
                        db.commit()
            except Exception as persist_err:
                logger.error(
                    "Episode %s: failed to persist generation metadata before "
                    "workflow dispatch: %s",
                    episode_id, persist_err,
                )

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
                return generation_result

            # Trigger the full workflow: S3 upload → [composition] → [distribution]
            # Isolated try/except so a broker hiccup cannot mark a successful
            # generation as "failed" or orphan the audio file.
            logger.info(
                "Episode %s: triggering workflow chain "
                "(composition=%s, distribution=%s, platforms=%s)",
                episode_id, enable_composition, enable_distribution,
                list(platforms.keys()) if platforms else [],
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
            except Exception as broker_err:
                logger.critical(
                    "Celery broker unavailable after successful generation for "
                    "episode %s — workflow chain could not be dispatched: %s",
                    episode_id, broker_err,
                )
        else:
            # Default path: simple S3 upload + DB update via finalization task.
            # Isolated try/except: a broker hiccup must not mark a successful
            # generation as "failed" or orphan the audio file.
            try:
                finalize_episode_generation_task.delay(
                    episode_id=episode_id,
                    generation_result=generation_result,
                )
            except Exception as broker_err:
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
                except Exception as sync_err:
                    logger.critical(
                        "Synchronous finalization also failed for episode %s: %s",
                        episode_id, sync_err,
                    )

        return generation_result

    except Exception as e:
        logger.warning(
            f"Podcast generation error for episode {episode_id}, "
            f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
        )
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'stage': 'retrying',
                'progress': 0,
                'status': f'Retrying after error: {str(e)}'
            }
        )
        try:
            raise self.retry(exc=e, countdown=calculate_backoff(self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                f"Podcast generation failed after {self.max_retries} retries "
                f"for episode {episode_id}: {e}"
            )
            self.update_state(
                state='FAILURE',
                meta={
                    'episode_id': episode_id,
                    'stage': 'failed',
                    'progress': 0,
                    'status': f'Generation failed: {str(e)}'
                }
            )
            return {
                "status": "failed",
                "audio_file_path": None,
                "transcript_path": None,
                "duration_seconds": 0,
                "file_size_bytes": 0,
                "error": str(e)
            }


@celery_app.task(bind=True, name="finalize_episode_generation", time_limit=360, max_retries=3)
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
                logger.info(
                    f"AWS_S3_BUCKET not configured, skipping S3 upload for episode {episode_id}"
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
            db.commit()

            logger.info(f"Episode {episode_id} finalized successfully")
            return {
                "status": "success",
                "episode_id": episode_id,
                "s3_url": s3_url,
                "s3_key": s3_key,
                "file_path": audio_file_path,
                "duration_seconds": duration_seconds,
                "file_size_bytes": file_size_bytes,
            }

        except Exception as e:
            logger.warning(
                f"Finalization error for episode {episode_id}, "
                f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
            )
            try:
                raise self.retry(exc=e, countdown=calculate_backoff(self.request.retries))
            except self.MaxRetriesExceededError:
                logger.error(
                    f"Finalization failed after {self.max_retries} retries "
                    f"for episode {episode_id}: {e}"
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
                except Exception as db_err:
                    logger.error(f"Failed to update episode status after error: {db_err}")
                return {"status": "failed", "error": str(e)}


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
		composed_output = output_path or f"/tmp/composed_{episode_id}.mp3"
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

	workflow = chain(*workflow_tasks)
	workflow.link(on_workflow_complete.s(episode_id=episode_id))
	workflow.link_error(
		on_workflow_failure.s(episode_id=episode_id, task_name="workflow")
	)

	return workflow
