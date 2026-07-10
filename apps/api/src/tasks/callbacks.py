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
from sqlalchemy import select

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.storage_deletion_outbox import StorageDeletionOutbox
from src.tasks.s3_upload import _cleanup_temp_file
from src.worker import celery_app

logger = logging.getLogger(__name__)


def _queue_orphaned_storage(
	s3_key: Optional[str] = None,
	file_path: Optional[str] = None,
	tenant_id: Optional[uuid_module.UUID] = None,
) -> None:
	"""Queue a still-existing storage artifact for deletion when its episode
	row is gone (issue #366).

	Closes the TOCTOU window where a Celery task persists an S3 object or
	local file *after* the episode row it belongs to (and any keys a delete
	flow collected) has already been deleted. Without this the artifact would
	be orphaned forever — IAM has no s3:ListBucket, so orphans are unfindable.
	Opens its own session: the caller's session may already be in a failed
	transaction state.
	"""
	if not s3_key and not file_path:
		return
	try:
		with SyncSessionLocal() as db:
			db.add(StorageDeletionOutbox(tenant_id=tenant_id, s3_key=s3_key, file_path=file_path))
			db.commit()
	except Exception as exc:
		logger.error(
			"Failed to queue orphaned storage (s3_key=%s, file_path=%s) for deletion: %s",
			s3_key, file_path, exc, exc_info=True,
		)


def _utcnow_iso() -> str:
	"""Return current UTC time as ISO 8601 string."""
	return datetime.now(timezone.utc).isoformat()


def _get_episode_for_update(db: Any, episode_id: str) -> Optional[Episode]:
	"""
	Fetch an Episode with a row-level lock (SELECT ... FOR UPDATE).

	Callbacks read-modify-write the ``generation_progress`` JSONB column. The
	per-platform distribution callbacks run as independent Celery tasks that can
	overlap, so an unlocked read-modify-write loses updates (issue #276). Locking
	the row serializes concurrent callbacks: the second blocks until the first
	commits, then re-reads the merged value. The lock is released on commit.
	"""
	return db.execute(
		select(Episode).where(Episode.id == uuid_module.UUID(episode_id)).with_for_update()
	).scalar_one_or_none()


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
			episode = _get_episode_for_update(db, episode_id)
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

	s3_key = result.get("s3_key")
	try:
		with SyncSessionLocal() as db:
			episode = _get_episode_for_update(db, episode_id)
			if episode is None:
				# The episode was deleted after this upload started (issue #366):
				# the object just landed in S3 with nothing left to reference it.
				logger.error("Episode %s not found in database", episode_id)
				_queue_orphaned_storage(s3_key=s3_key)
				return

			# Do NOT set generation_status here: upload has already completed, so
			# "uploading" would briefly regress the status. The workflow chain's
			# next task (or on_workflow_complete) owns status progression (issue #220).
			episode.s3_url = result.get("s3_url")
			episode.s3_key = s3_key
			current_progress = dict(episode.generation_progress or {})
			current_progress.update({
				"upload": "complete",
				"uploaded_at": _utcnow_iso(),
			})
			episode.generation_progress = current_progress
			db.commit()
	except Exception as exc:
		logger.error(
			"Failed to update episode %s: %s", episode_id, exc, exc_info=True
		)
		return

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

	composed_path = result.get("output_path")
	old_file_path: Optional[str] = None
	try:
		with SyncSessionLocal() as db:
			episode = _get_episode_for_update(db, episode_id)
			if episode is None:
				logger.error("Episode %s not found in database", episode_id)
				return

			# Capture the pre-composition path before overwriting it: the composed
			# file supersedes the raw generated audio, so its per-run temp dir
			# (audio + transcript) is now disposable (issue #309).
			old_file_path = episode.file_path

			episode.file_path = composed_path
			# Persist the composed duration to the column so distribution publishes
			# the composed length, not the pre-composition one (issue #211).
			episode.duration_seconds = result.get("duration_seconds")
			episode.generation_status = "composing"
			current_progress = dict(episode.generation_progress or {})
			current_progress.update({
				"composition": "complete",
				"duration_seconds": result.get("duration_seconds"),
				"composed_at": _utcnow_iso(),
			})
			episode.generation_progress = current_progress
			db.commit()
	except Exception as exc:
		logger.error(
			"Failed to update episode %s: %s", episode_id, exc, exc_info=True
		)
		return

	if old_file_path and old_file_path != composed_path:
		_cleanup_temp_file(old_file_path)

	logger.info(
		"Episode %s composition complete: %.1fs",
		episode_id,
		result.get("duration_seconds", 0),
	)


def record_platform_distribution(
	episode_id: str, platform: str, result: Dict[str, Any]
) -> bool:
	"""
	Merge a platform's distribution outcome into Episode.generation_progress
	under a row lock and commit.

	Shared by the on_distribution_complete callback and the distribution task's
	in-task success recording (issue #312) so both writes produce an identical
	entry shape — the second write is an idempotent re-merge of the first.

	Returns:
		True if the episode was found and updated, False otherwise.
	"""
	failed = result.get("status") != "success"
	with SyncSessionLocal() as db:
		episode = _get_episode_for_update(db, episode_id)
		if episode is None:
			logger.error("Episode %s not found in database", episode_id)
			return False

		current_progress = dict(episode.generation_progress or {})
		distribution = dict(current_progress.get("distribution", {}))
		if failed:
			distribution[platform] = {
				"status": "failed",
				"error": result.get("error"),
				"failed_at": _utcnow_iso(),
			}
		else:
			distribution[platform] = {
				"status": "complete",
				"platform_episode_id": result.get("platform_episode_id"),
				"platform_url": result.get("platform_url"),
				"distributed_at": _utcnow_iso(),
			}
		current_progress["distribution"] = distribution
		episode.generation_progress = current_progress
		if not failed:
			episode.generation_status = "distributing"

		db.commit()
	return True


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
	failed = result.get("status") != "success"
	if failed:
		# Permanently-failed distribution tasks return {status: failed} rather than
		# raising (to keep per-platform distribution independent), so record the
		# failure here instead of dropping it. The whole-episode generation_status
		# is left untouched — on_workflow_complete derives the terminal state from
		# the recorded per-platform outcomes (issue #300).
		logger.error(
			"Distribution to %s for episode %s indicates failure: %s",
			platform,
			episode_id,
			result.get("error"),
		)

	try:
		if not record_platform_distribution(episode_id, platform, result):
			return

		if not failed:
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

	Sets Episode.generation_status to 'complete' when every distributed platform
	succeeded, or 'distribution_failed' when any platform's recorded outcome is
	non-success — so a partially-failed run is not reported as fully published
	(issue #300). The locked read is done inline (not via _update_episode) because
	the final status depends on the per-platform outcomes already in the row.
	"""
	try:
		with SyncSessionLocal() as db:
			episode = _get_episode_for_update(db, episode_id)
			if episode is None:
				logger.error("Episode %s not found in database", episode_id)
				return

			current_progress = dict(episode.generation_progress or {})
			distribution = current_progress.get("distribution", {})
			failed_platforms = [
				platform
				for platform, entry in distribution.items()
				if (entry or {}).get("status") != "complete"
			]

			completed_at = _utcnow_iso()
			if failed_platforms:
				episode.generation_status = "distribution_failed"
				current_progress["status"] = "distribution_failed"
				current_progress["failed_platforms"] = failed_platforms
			else:
				episode.generation_status = "complete"
				current_progress["status"] = "complete"
				# Clear any stale marker from a prior distribution_failed run that
				# has since been retried successfully (issue #300).
				current_progress.pop("failed_platforms", None)
			current_progress["completed_at"] = completed_at
			episode.generation_progress = current_progress

			db.commit()

		if failed_platforms:
			logger.error(
				"Episode %s workflow completed with failed distributions: %s",
				episode_id,
				", ".join(failed_platforms),
			)
		else:
			logger.info("Episode %s workflow completed successfully", episode_id)
	except Exception as exc:
		logger.error(
			"Failed to finalize episode %s: %s", episode_id, exc, exc_info=True
		)


# ---------------------------------------------------------------------------
# Error callback
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="on_workflow_failure")
def on_workflow_failure(
	self: Task,
	task_id: str,
	exc: Any = None,
	traceback: Any = None,
	episode_id: str = "",
	task_name: str = "unknown",
) -> None:
	"""
	Error callback fired when any task in the workflow fails.

	Sets Episode.generation_status = 'failed' and records the error in
	generation_progress.

	Celery invokes ``bind=True`` error callbacks "old style": only the failed
	task's id is passed positionally — ``exc``/``traceback`` are *not* (see
	``BaseBackend._call_task_errbacks``, which routes bound errbacks via the
	single-arg path). They therefore default to None and are recovered from the
	result backend below, so this works both as a ``link_error`` on a real task
	and when called directly with explicit args (issue #294).

	Args:
		self: Celery task instance.
		task_id: ID of the failed task.
		exc: Exception that was raised (may be serialised to str by Celery).
		traceback: Full traceback string.
		episode_id: UUID string of the episode.
		task_name: Human-readable name of the task that failed.
	"""
	if exc is None and task_id:
		# Old-style errback: pull the failure detail from the result backend so
		# the recorded message is meaningful rather than "... failed: None".
		try:
			from celery.result import AsyncResult

			ar = AsyncResult(str(task_id), app=self.app)
			exc = ar.result
			traceback = traceback or ar.traceback
		except Exception:  # pragma: no cover - backend best-effort
			logger.debug("Could not fetch failure detail for task %s", task_id)

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
