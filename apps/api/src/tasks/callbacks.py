"""
Celery callback tasks for updating Episode status after workflow steps complete.

These tasks are triggered by Celery's link/link_error mechanism and update the
Episode record in the database with the results of each workflow stage.
"""
import logging
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from celery import Task

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.worker import celery_app

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
	"""Return current UTC time as ISO 8601 string."""
	return datetime.now(timezone.utc).isoformat()


def _update_episode(
	episode_id: str,
	updates: Dict[str, Any],
	progress_updates: Optional[Dict[str, Any]] = None,
) -> bool:
	"""
	Fetch an Episode from the database and apply updates atomically.

	Args:
		episode_id: UUID string of the episode to update.
		updates: Dict of Episode column name → new value.
		progress_updates: Dict merged into Episode.generation_progress JSONB.

	Returns:
		True if the episode was found and updated, False otherwise.
	"""
	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("Episode %s not found in database", episode_id)
				return False

			for attr, value in updates.items():
				setattr(episode, attr, value)

			if progress_updates:
				current_progress = dict(episode.generation_progress or {})
				current_progress.update(progress_updates)
				episode.generation_progress = current_progress

			db.commit()
			return True
	except Exception as exc:
		logger.error(
			"Failed to update episode %s: %s", episode_id, exc, exc_info=True
		)
		return False


# ---------------------------------------------------------------------------
# Success callbacks
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="on_upload_complete")
def on_upload_complete(self: Task, result: Dict[str, Any], episode_id: str) -> None:
	"""
	Callback fired when upload_to_s3_task completes successfully.

	Updates Episode.s3_url, s3_key, and generation_progress.

	Args:
		self: Celery task instance.
		result: Result dict from upload_to_s3_task.
		episode_id: UUID string of the episode.
	"""
	if result.get("status") != "success":
		logger.error(
			"Upload result for episode %s indicates failure: %s",
			episode_id,
			result.get("error"),
		)
		return

	updated = _update_episode(
		episode_id,
		updates={
			"s3_url": result.get("s3_url"),
			"s3_key": result.get("s3_key"),
			"generation_status": "uploading",
		},
		progress_updates={
			"upload": "complete",
			"uploaded_at": _utcnow_iso(),
		},
	)
	if updated:
		logger.info(
			"Episode %s updated with S3 URL: %s", episode_id, result.get("s3_url")
		)


@celery_app.task(bind=True, name="on_composition_complete")
def on_composition_complete(self: Task, result: Dict[str, Any], episode_id: str) -> None:
	"""
	Callback fired when merge_audio_snippets_task completes successfully.

	Updates Episode.file_path, duration_seconds, and generation_progress.

	Args:
		self: Celery task instance.
		result: Result dict from merge_audio_snippets_task.
		episode_id: UUID string of the episode.
	"""
	if result.get("status") != "success":
		logger.error(
			"Composition result for episode %s indicates failure: %s",
			episode_id,
			result.get("error"),
		)
		return

	updated = _update_episode(
		episode_id,
		updates={
			"file_path": result.get("output_path"),
			# Persist the composed duration to the column so distribution publishes
			# the composed length, not the pre-composition one (issue #211).
			"duration_seconds": result.get("duration_seconds"),
			"generation_status": "composing",
		},
		progress_updates={
			"composition": "complete",
			"duration_seconds": result.get("duration_seconds"),
			"composed_at": _utcnow_iso(),
		},
	)
	if updated:
		logger.info(
			"Episode %s composition complete: %.1fs",
			episode_id,
			result.get("duration_seconds", 0),
		)


@celery_app.task(bind=True, name="on_distribution_complete")
def on_distribution_complete(
	self: Task, result: Dict[str, Any], episode_id: str, platform: str
) -> None:
	"""
	Callback fired when distribute_to_platform_task completes successfully.

	Updates Episode.generation_progress with platform distribution results.

	Args:
		self: Celery task instance.
		result: Result dict from distribute_to_platform_task.
		episode_id: UUID string of the episode.
		platform: Platform name (e.g. 'spotify', 'apple_podcasts', 'webhook').
	"""
	if result.get("status") != "success":
		logger.error(
			"Distribution to %s for episode %s indicates failure: %s",
			platform,
			episode_id,
			result.get("error"),
		)
		return

	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("Episode %s not found in database", episode_id)
				return

			current_progress = dict(episode.generation_progress or {})
			distribution = dict(current_progress.get("distribution", {}))
			distribution[platform] = {
				"status": "complete",
				"platform_episode_id": result.get("platform_episode_id"),
				"platform_url": result.get("platform_url"),
				"distributed_at": _utcnow_iso(),
			}
			current_progress["distribution"] = distribution
			episode.generation_progress = current_progress
			episode.generation_status = "distributing"

			db.commit()

		logger.info(
			"Episode %s distributed to %s: platform_id=%s",
			episode_id,
			platform,
			result.get("platform_episode_id"),
		)
	except Exception as exc:
		logger.error(
			"Failed to update episode %s after distribution to %s: %s",
			episode_id,
			platform,
			exc,
			exc_info=True,
		)


@celery_app.task(bind=True, name="on_workflow_complete")
def on_workflow_complete(self: Task, result: Dict[str, Any], episode_id: str) -> None:
	"""
	Callback fired when the entire podcast workflow completes successfully.

	Sets Episode.generation_status = 'complete'.

	Args:
		self: Celery task instance.
		result: Final result from the last task in the workflow chain.
		episode_id: UUID string of the episode.
	"""
	updated = _update_episode(
		episode_id,
		updates={"generation_status": "complete"},
		progress_updates={
			"status": "complete",
			"completed_at": _utcnow_iso(),
		},
	)
	if updated:
		logger.info("Episode %s workflow completed successfully", episode_id)


# ---------------------------------------------------------------------------
# Error callback
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="on_workflow_failure")
def on_workflow_failure(
	self: Task,
	task_id: str,
	exc: Any,
	traceback: Any,
	episode_id: str,
	task_name: str = "unknown",
) -> None:
	"""
	Error callback fired when any task in the workflow fails.

	Sets Episode.generation_status = 'failed' and records the error in
	generation_progress.

	This task uses Celery's link_error signature: the first three positional
	arguments after ``self`` are task_id, exc, and traceback as passed by Celery.

	Args:
		self: Celery task instance.
		task_id: ID of the failed task.
		exc: Exception that was raised (may be serialised to str by Celery).
		traceback: Full traceback string.
		episode_id: UUID string of the episode.
		task_name: Human-readable name of the task that failed.
	"""
	error_message = f"Task '{task_name}' failed: {exc}"
	updated = _update_episode(
		episode_id,
		updates={"generation_status": "failed"},
		progress_updates={
			"status": "failed",
			"failed_task": task_name,
			"error_message": error_message,
			"failed_at": _utcnow_iso(),
		},
	)
	if updated:
		logger.error(
			"Episode %s workflow failed at task '%s': %s", episode_id, task_name, exc
		)
