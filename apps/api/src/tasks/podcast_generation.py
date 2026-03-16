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
from src.tasks.retry_utils import calculate_backoff

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_podcast", time_limit=600, max_retries=3)
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
	s3_key = f"podcasts/episode-{episode_id}.mp3"

	# Stage: S3 upload
	upload_sig = upload_to_s3_task.s(
		file_path=audio_file_path,
		s3_key=s3_key,
		bucket_name=bucket,
		content_type="audio/mpeg",
	).set(
		link=on_upload_complete.s(episode_id=episode_id),
		link_error=on_workflow_failure.s(episode_id=episode_id, task_name="upload_to_s3"),
	)

	workflow_tasks = [upload_sig]

	# Stage: audio composition (optional)
	if enable_composition:
		composed_output = output_path or f"/tmp/composed_{episode_id}.mp3"
		composition_sig = merge_audio_snippets_task.s(
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

	# Stage: platform distribution (optional)
	if enable_distribution and platforms:
		for platform_name, platform_config in platforms.items():
			dist_sig = distribute_to_platform_task.s(
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
