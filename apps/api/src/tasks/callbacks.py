"""
Celery callback tasks for episode workflow chaining (GAP-028).

These tasks are designed to be used as Celery `.link()` (success) and
`.link_error()` (failure) callbacks when building task chains.

Success callback signature (via `.link()`):
    task receives `result` dict as first positional arg (the parent task's
    return value), plus keyword args supplied by `.s(...)` partial.

Failure callback signature (via `.link_error()`):
    Celery passes the failed task's ID as the first positional arg (`task_id`),
    plus keyword args supplied by `.s(...)` partial.
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


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
	"""Return the current UTC time as an ISO-8601 string."""
	return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Success callbacks
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="on_upload_complete")
def on_upload_complete(
	self: Task,
	result: Dict[str, Any],
	episode_id: str,
) -> None:
	"""
	Callback fired when upload_to_s3_task completes successfully.

	Updates Episode.s3_url, Episode.s3_key, and sets generation_status to
	'uploading' (the intermediate state after a successful S3 upload; the
	final 'complete' is set by on_workflow_complete).

	Args:
		self: Celery task instance
		result: Return value of upload_to_s3_task
		episode_id: UUID string of the episode to update
	"""
	if result.get("status") != "success":
		logger.error(
			"on_upload_complete: upload reported failure for episode %s — skipping DB update. "
			"error=%s",
			episode_id, result.get("error"),
		)
		return

	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("on_upload_complete: episode %s not found", episode_id)
				return

			episode.s3_url = result.get("s3_url")
			episode.s3_key = result.get("s3_key")
			episode.generation_status = "uploading"
			episode.generation_progress = {
				**dict(episode.generation_progress or {}),
				"upload": "complete",
				"uploaded_at": _utcnow_iso(),
			}
			db.commit()

			logger.info(
				"on_upload_complete: episode %s updated — s3_url=%s",
				episode_id, episode.s3_url,
			)

	except Exception:
		logger.exception(
			"on_upload_complete: unexpected error updating episode %s", episode_id
		)


@celery_app.task(bind=True, name="on_composition_complete")
def on_composition_complete(
	self: Task,
	result: Dict[str, Any],
	episode_id: str,
) -> None:
	"""
	Callback fired when merge_audio_snippets_task completes successfully.

	Updates Episode.file_path, generation_status, and records composition
	metadata in generation_progress.

	Args:
		self: Celery task instance
		result: Return value of merge_audio_snippets_task
		episode_id: UUID string of the episode to update
	"""
	if result.get("status") != "success":
		logger.error(
			"on_composition_complete: composition reported failure for episode %s — "
			"skipping DB update. error=%s",
			episode_id, result.get("error"),
		)
		return

	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("on_composition_complete: episode %s not found", episode_id)
				return

			episode.file_path = result.get("output_path")
			episode.generation_status = "composing"
			episode.generation_progress = {
				**dict(episode.generation_progress or {}),
				"composition": "complete",
				"duration_seconds": result.get("duration_seconds"),
				"composed_at": _utcnow_iso(),
			}
			db.commit()

			logger.info(
				"on_composition_complete: episode %s composition complete — "
				"duration=%.1fs",
				episode_id, result.get("duration_seconds", 0),
			)

	except Exception:
		logger.exception(
			"on_composition_complete: unexpected error updating episode %s", episode_id
		)


@celery_app.task(bind=True, name="on_distribution_complete")
def on_distribution_complete(
	self: Task,
	result: Dict[str, Any],
	episode_id: str,
	platform: str,
) -> None:
	"""
	Callback fired when distribute_to_platform_task completes successfully.

	Stores the platform-specific episode ID in generation_progress['distribution'].
	Multiple platforms accumulate without overwriting each other.

	Args:
		self: Celery task instance
		result: Return value of distribute_to_platform_task
		episode_id: UUID string of the episode to update
		platform: Platform name (e.g. 'spotify', 'apple_podcasts', 'webhook')
	"""
	if result.get("status") != "success":
		logger.error(
			"on_distribution_complete: distribution to %s reported failure for "
			"episode %s — skipping DB update. error=%s",
			platform, episode_id, result.get("error"),
		)
		return

	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("on_distribution_complete: episode %s not found", episode_id)
				return

			progress = dict(episode.generation_progress or {})
			distribution = dict(progress.get("distribution", {}))
			distribution[platform] = result.get("platform_episode_id")
			progress["distribution"] = distribution
			episode.generation_progress = progress
			db.commit()

			logger.info(
				"on_distribution_complete: episode %s distributed to %s — id=%s",
				episode_id, platform, result.get("platform_episode_id"),
			)

	except Exception:
		logger.exception(
			"on_distribution_complete: unexpected error updating episode %s", episode_id
		)


@celery_app.task(bind=True, name="on_workflow_complete")
def on_workflow_complete(
	self: Task,
	result: Dict[str, Any],
	episode_id: str,
) -> None:
	"""
	Callback fired when the entire episode workflow completes successfully.

	Sets Episode.generation_status = 'complete' and records a completion
	timestamp in generation_progress.

	Args:
		self: Celery task instance
		result: Final result dict from the last task in the chain
		episode_id: UUID string of the episode to finalize
	"""
	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("on_workflow_complete: episode %s not found", episode_id)
				return

			episode.generation_status = "complete"
			episode.generation_progress = {
				**dict(episode.generation_progress or {}),
				"status": "published",
				"completed_at": _utcnow_iso(),
			}
			db.commit()

			logger.info("on_workflow_complete: episode %s workflow complete", episode_id)

	except Exception:
		logger.exception(
			"on_workflow_complete: unexpected error updating episode %s", episode_id
		)


# ---------------------------------------------------------------------------
# Failure callback (errback)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="on_workflow_failure")
def on_workflow_failure(
	self: Task,
	task_id: str,
	episode_id: str,
	task_name: Optional[str] = None,
) -> None:
	"""
	Errback fired when any task in the workflow fails (via .link_error()).

	Celery calls link_error callbacks with the failed task's ID as the first
	positional argument.  Additional keyword arguments (episode_id, task_name)
	are supplied via the partial created with `.s(...)`.

	Sets Episode.generation_status = 'failed' and records failure metadata in
	generation_progress.

	Args:
		self: Celery task instance
		task_id: Celery task ID of the failed task (provided by Celery)
		episode_id: UUID string of the episode to mark as failed
		task_name: Human-readable name of the task that failed (optional)
	"""
	try:
		with SyncSessionLocal() as db:
			episode = db.get(Episode, uuid_module.UUID(episode_id))
			if episode is None:
				logger.error("on_workflow_failure: episode %s not found", episode_id)
				return

			episode.generation_status = "failed"
			episode.generation_progress = {
				**dict(episode.generation_progress or {}),
				"status": "failed",
				"failed_task": task_name,
				"failed_at": _utcnow_iso(),
				"failed_celery_task_id": task_id,
			}
			db.commit()

			logger.error(
				"on_workflow_failure: episode %s workflow failed at task '%s' "
				"(celery_task_id=%s)",
				episode_id, task_name, task_id,
			)

	except Exception:
		logger.exception(
			"on_workflow_failure: unexpected error updating episode %s", episode_id
		)
