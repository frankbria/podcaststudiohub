"""
Celery callback tasks for workflow completion and error handling.

These tasks are used as success and error callbacks in the podcast
generation workflow chain (GAP-026).
"""
import uuid as uuid_module
import logging
from celery import Task
from typing import Any, Dict, Optional

from src.worker import celery_app
from src.config import settings
from src.database import SyncSessionLocal
from src.models.episode import Episode

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="update_episode_on_success")
def update_episode_on_success(
	self: Task,
	episode_id: str,
	audio_file_path: Optional[str] = None,
	transcript_path: Optional[str] = None,
	duration_seconds: float = 0,
	file_size_bytes: int = 0,
	s3_key: Optional[str] = None,
	bucket_name: Optional[str] = None,
) -> Dict[str, Any]:
	"""
	Finalize episode in the database after a successful workflow run.

	Updates Episode with file metadata, S3 URL, and sets generation_status
	to 'complete'. This task is the last step in the workflow chain.

	Args:
		self: Celery task instance
		episode_id: UUID of the episode
		audio_file_path: Local path to the generated audio file
		transcript_path: Local path to the generated transcript
		duration_seconds: Audio duration
		file_size_bytes: Audio file size
		s3_key: S3 object key for the uploaded audio
		bucket_name: S3 bucket name (used to construct the public URL)

	Returns:
		Dictionary with finalization results
	"""
	logger.info(
		"Workflow completed successfully for episode %s (stage 'complete')",
		episode_id,
	)

	# Build S3 URL from key and bucket
	s3_url = None
	if s3_key and bucket_name:
		region = settings.AWS_REGION
		if region == "us-east-1":
			s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
		else:
			s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"

	with SyncSessionLocal() as db:
		try:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("Episode %s not found in database", episode_id)
				return {"status": "failed", "error": f"Episode {episode_id} not found"}

			episode.file_path = audio_file_path
			episode.transcript_path = transcript_path
			episode.duration_seconds = duration_seconds
			episode.file_size_bytes = file_size_bytes
			episode.s3_url = s3_url
			episode.s3_key = s3_key
			episode.generation_status = "complete"
			episode.generation_progress = {
				**dict(episode.generation_progress or {}),
				"stage": "complete",
				"progress": 100,
				"status": "Workflow completed successfully",
			}
			db.commit()

			logger.info("Episode %s marked as complete", episode_id)
			return {
				"status": "success",
				"episode_id": episode_id,
				"s3_url": s3_url,
				"s3_key": s3_key,
				"file_path": audio_file_path,
				"duration_seconds": duration_seconds,
				"file_size_bytes": file_size_bytes,
			}

		except Exception as exc:
			logger.error(
				"Failed to update episode %s on workflow success: %s",
				episode_id, exc,
			)
			try:
				db.rollback()
			except Exception:
				pass
			return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="update_episode_on_failure")
def update_episode_on_failure(
	self: Task,
	episode_id: str,
	error: Optional[str] = None,
) -> Dict[str, Any]:
	"""
	Mark episode as failed in the database after a workflow error.

	Updates Episode.generation_status = 'failed' and stores the error
	message in Episode.error_message. Called via Celery link_error when
	any task in the workflow chain raises an exception.

	Args:
		self: Celery task instance
		episode_id: UUID of the episode
		error: Human-readable error description

	Returns:
		Dictionary with failure details
	"""
	logger.error(
		"Workflow failed for episode %s: %s",
		episode_id, error,
	)

	with SyncSessionLocal() as db:
		try:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("Episode %s not found in database", episode_id)
				return {"status": "failed", "error": f"Episode {episode_id} not found"}

			episode.generation_status = "failed"
			episode.error_message = error
			episode.generation_progress = {
				**dict(episode.generation_progress or {}),
				"stage": "failed",
				"error_message": error,
			}
			db.commit()

			logger.info("Episode %s marked as failed", episode_id)
			return {"status": "failed", "episode_id": episode_id, "error": error}

		except Exception as exc:
			logger.error(
				"Failed to update episode %s on workflow failure: %s",
				episode_id, exc,
			)
			try:
				db.rollback()
			except Exception:
				pass
			return {"status": "failed", "error": str(exc)}
