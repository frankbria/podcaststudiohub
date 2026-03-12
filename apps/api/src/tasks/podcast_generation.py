"""
Celery tasks for podcast generation
Wraps the existing podcastfy CLI functionality
"""
import os
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

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_podcast", time_limit=600)
def generate_podcast_task(
    self: Task,
    episode_id: str,
    urls: Optional[List[str]] = None,
    text_content: Optional[str] = None,
    file_paths: Optional[List[str]] = None,
    image_paths: Optional[List[str]] = None,
    youtube_urls: Optional[List[str]] = None,
    topic: Optional[str] = None,
    tts_model: str = "openai",
    conversation_config: Optional[Dict[str, Any]] = None,
    longform: bool = False
) -> Dict[str, Any]:
    """
    Generate a podcast episode using the existing Podcastfy CLI.

    This task wraps the existing generate_podcast() function from the CLI
    and provides progress tracking for the GUI.

    Args:
        self: Celery task instance (for progress updates)
        episode_id: UUID of the episode being generated
        urls: List of URLs to extract content from
        text_content: Raw text content
        file_paths: List of file paths (PDFs, documents, etc.)
        image_paths: List of image file paths
        youtube_urls: List of YouTube URLs
        topic: Topic for content generation (uses web search)
        tts_model: TTS provider (openai, elevenlabs, gemini, etc.)
        conversation_config: Custom conversation configuration
        longform: Whether to generate long-form content

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

        # Import the existing CLI function
        # Note: This imports from the existing podcastfy package
        import sys
        # Add the root directory to path to import podcastfy
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

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

        # Generate the podcast using existing CLI
        result = generate_podcast(
            urls=urls,
            text=text_content,
            file=file_paths,
            image_paths=image_paths,
            youtube_urls=youtube_urls,
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

        # Chain the finalization task (S3 upload + DB update).
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
        logger.error(f"Podcast generation failed for episode {episode_id}: {str(e)}")
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


@celery_app.task(bind=True, name="finalize_episode_generation", time_limit=360)
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

                # Build S3 key using consistent naming convention
                s3_key = f"podcasts/user-{episode.user_id}/episode-{episode_id}.mp3"

                upload_result = upload_to_s3_task(
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
            logger.error(f"Error finalizing episode {episode_id}: {str(e)}")
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


# ---------------------------------------------------------------------------
# Workflow builder
# ---------------------------------------------------------------------------

def build_generation_workflow(
	episode_id: str,
	audio_file_path: str,
	enable_composition: bool = False,
	timeline: Optional[List[Dict[str, Any]]] = None,
	output_path: Optional[str] = None,
	enable_distribution: bool = False,
	platforms: Optional[Dict[str, Dict[str, Any]]] = None,
	episode_metadata: Optional[Dict[str, Any]] = None,
) -> chain:
	"""
	Build a Celery chain for the post-generation workflow.

	The chain is assembled from the optional stages that are enabled:

	1. upload_to_s3_task (when AWS_S3_BUCKET is configured)
	2. merge_audio_snippets_task (when enable_composition is True)
	3. distribute_to_platform_task × N (when enable_distribution is True)
	4. on_workflow_complete (always — marks episode as complete)

	Each stage is linked with an on_workflow_failure errback so that any
	failure marks the episode as failed in the database.

	Args:
		episode_id: UUID string of the episode being processed
		audio_file_path: Local path of the generated audio file
		enable_composition: Whether to include audio composition stage
		timeline: Timeline segments for composition (required when enable_composition=True)
		output_path: Output path for composed audio (required when enable_composition=True)
		enable_distribution: Whether to include platform distribution stage
		platforms: Mapping of platform_name → platform_config dicts
		episode_metadata: Metadata dict to pass to distribution tasks

	Returns:
		A Celery chain canvas ready for `.apply_async()` or `.delay()`.
	"""
	# Import here to avoid circular imports (callbacks imports from worker,
	# which imports from tasks; keeping imports local breaks the cycle).
	from src.tasks.callbacks import (
		on_upload_complete,
		on_composition_complete,
		on_distribution_complete,
		on_workflow_complete,
		on_workflow_failure,
	)
	from src.tasks.audio_composition import merge_audio_snippets_task
	from src.tasks.platform_distribution import distribute_to_platform_task

	workflow_tasks: List[Any] = []

	# ------------------------------------------------------------------
	# Stage 1: S3 upload (conditional on bucket being configured)
	# ------------------------------------------------------------------
	if settings.AWS_S3_BUCKET:
		s3_key = f"podcasts/episode-{episode_id}.mp3"
		upload_sig = upload_to_s3_task.si(
			file_path=audio_file_path,
			s3_key=s3_key,
			bucket_name=settings.AWS_S3_BUCKET,
			content_type="audio/mpeg",
		).set(
			link=on_upload_complete.s(episode_id=episode_id),
			link_error=on_workflow_failure.s(
				episode_id=episode_id, task_name="upload_to_s3"
			),
		)
		workflow_tasks.append(upload_sig)

	# ------------------------------------------------------------------
	# Stage 2: Audio composition (optional)
	# ------------------------------------------------------------------
	if enable_composition:
		compose_sig = merge_audio_snippets_task.si(
			episode_id=episode_id,
			timeline=timeline or [],
			output_path=output_path or f"/tmp/composed_{episode_id}.mp3",
		).set(
			link=on_composition_complete.s(episode_id=episode_id),
			link_error=on_workflow_failure.s(
				episode_id=episode_id, task_name="merge_audio_snippets"
			),
		)
		workflow_tasks.append(compose_sig)

	# ------------------------------------------------------------------
	# Stage 3: Platform distribution (optional, one task per platform)
	# ------------------------------------------------------------------
	if enable_distribution and platforms:
		for platform_name, platform_config in platforms.items():
			dist_sig = distribute_to_platform_task.si(
				episode_id=episode_id,
				platform=platform_name,
				platform_config=platform_config,
				episode_metadata=episode_metadata or {},
			).set(
				link=on_distribution_complete.s(
					episode_id=episode_id, platform=platform_name
				),
				link_error=on_workflow_failure.s(
					episode_id=episode_id,
					task_name=f"distribute_{platform_name}",
				),
			)
			workflow_tasks.append(dist_sig)

	# ------------------------------------------------------------------
	# Final: mark workflow as complete
	# ------------------------------------------------------------------
	complete_sig = on_workflow_complete.si(
		result={"status": "success", "episode_id": episode_id},
		episode_id=episode_id,
	)
	workflow_tasks.append(complete_sig)

	return chain(*workflow_tasks)
