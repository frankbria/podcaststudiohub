"""
Celery tasks for S3 file uploads
"""
import os
import shutil
import tempfile
import logging
from celery import Task
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError

from src.worker import celery_app
from src.config import settings
from src.tasks.content_review import CONTENT_REVIEW_METADATA, held_episode_of
from src.tasks.retry_utils import calculate_backoff

logger = logging.getLogger(__name__)

# Per-run directory prefix used by generate_podcast_task for the engine's
# audio output under the system temp dir (issue #309). The value predates the
# #543 cut-over and is kept so cleanup still recognises older run dirs. Cleanup
# recognizes this prefix and removes the whole run dir, not just the uploaded
# file, so the transcript beside it cannot leak.
GENERATION_RUN_DIR_PREFIX = "podcastfy-run-"


def _cleanup_temp_file(file_path: str) -> None:
    """Best-effort delete of a temp upload artifact once it is no longer needed.

    Only removes files under the system temp dir so it can never delete a
    persistent file (e.g. under ``data/``); never raises. When the file lives in
    a ``podcastfy-run-*`` per-run dir, the whole dir is removed (audio +
    transcript, issue #309). Call this only when the local copy is disposable:
    after a successful upload, or after retries are exhausted (no further retry
    will read it) — never on the retry path.
    """
    try:
        temp_root = os.path.realpath(tempfile.gettempdir())
        real = os.path.realpath(file_path)
        if os.path.commonpath([temp_root, real]) != temp_root:
            return
        parent = os.path.dirname(real)
        if (
            parent != temp_root
            and os.path.basename(parent).startswith(GENERATION_RUN_DIR_PREFIX)
            and os.path.isdir(parent)
        ):
            shutil.rmtree(parent)
            logger.info("Removed generation run dir: %s", parent)
        elif os.path.isfile(real):
            os.remove(real)
            logger.info("Removed temp upload artifact: %s", real)
    except Exception as exc:  # cleanup must never fail the task  # noqa: BLE001 — cleanup must never fail the task: the artifact is disposable and the upload result is already decided
        logger.warning("Failed to clean up temp file %s: %s", file_path, exc)


def _upload_extra_args(s3_key: str, content_type: str) -> Dict[str, Any]:
    """Upload options; held episode audio is marked so the public URL refuses it (#626)."""
    extra: Dict[str, Any] = {"ContentType": content_type}
    if held_episode_of(s3_key):
        extra["Metadata"] = {CONTENT_REVIEW_METADATA: "pending"}
    return extra


def _s3_object_url(bucket_name: str, s3_key: str) -> str:
    """Region-aware object URL (not publicly fetchable, see #385)."""
    region = settings.AWS_REGION
    if region == "us-east-1":
        # us-east-1 uses the legacy URL format without region subdomain
        return f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
    return f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"


_NON_RETRYABLE_CODES = frozenset({
    "NoSuchBucket", "InvalidAccessKeyId",
    "SignatureDoesNotMatch", "AccessDenied",
})


def _raise_if_non_retryable(error: ClientError, file_path: str) -> str:
    """Re-raise a permanent S3 error after cleanup; return a retryable one's code."""
    error_code = error.response.get("Error", {}).get("Code", "")
    if error_code in _NON_RETRYABLE_CODES:
        # Permanent errors are never retried — terminal failure, so the temp
        # artifact is disposable (re-running generation re-composes it).
        logger.error(f"S3 upload failed with non-retryable error ({error_code}): {error}")
        _cleanup_temp_file(file_path)
        raise error
    return error_code


def _retry_or_give_up(task: Task, error: Exception, file_path: str) -> None:
    """Retry the upload, or clean up and re-raise once retries are spent. Always raises.

    Decide terminality here rather than catching MaxRetriesExceededError.
    Celery only raises that when retry() is called WITHOUT exc=; with an exc it
    does `raise_with_context(exc)` instead (Task.retry, celery 5.6), so
    `except self.MaxRetriesExceededError` never fired and the cleanup that used
    to live inside it never ran — leaking the temp artifact on every exhausted
    upload (#498).
    """
    if task.request.retries >= task.max_retries:
        logger.error(f"S3 upload failed after {task.max_retries} retries for {file_path}: {error}")
        # Terminal: no further attempt will read the file.
        _cleanup_temp_file(file_path)
        raise error
    raise task.retry(exc=error, countdown=calculate_backoff(task.request.retries))


@celery_app.task(bind=True, name="upload_to_s3", time_limit=300, max_retries=3)
def upload_to_s3_task(
    self: Task,
    file_path: str,
    s3_key: str,
    bucket_name: str,
    content_type: str = "audio/mpeg"
) -> Dict[str, Any]:
    """
    Upload a file to AWS S3.

    Args:
        self: Celery task instance
        file_path: Local file path to upload
        s3_key: S3 object key (path in bucket)
        bucket_name: S3 bucket name
        content_type: MIME type of the file

    Returns:
        Dictionary with upload results including s3_url, s3_key, file_size_bytes
    """
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 0,
                'status': 'Starting S3 upload...'
            }
        )

        # Initialize S3 client
        s3_client = boto3.client('s3')

        # Get file size for progress tracking
        file_size = os.path.getsize(file_path)

        # s3transfer invokes Callback on its own threads, where Celery's
        # thread-local self.request is empty, so the id is captured here.
        task_id = self.request.id

        def upload_progress(bytes_transferred):
            progress = int((bytes_transferred / file_size) * 100)
            self.update_state(
                task_id=task_id,
                state='PROGRESS',
                meta={
                    'progress': progress,
                    'status': f'Uploading to S3... {progress}%'
                }
            )

        # Upload file
        s3_client.upload_file(
            file_path,
            bucket_name,
            s3_key,
            ExtraArgs=_upload_extra_args(s3_key, content_type),
            Callback=upload_progress
        )

        s3_url = _s3_object_url(bucket_name, s3_key)

        # Upload succeeded — the local copy is now disposable.
        _cleanup_temp_file(file_path)

        return {
            "status": "success",
            "s3_key": s3_key,
            "s3_url": s3_url,
            "file_size_bytes": file_size,
            "error": None
        }

    except ClientError as e:
        error_code = _raise_if_non_retryable(e, file_path)
        # Retryable S3 error — retry with exponential backoff
        logger.warning(
            f"Retryable S3 error ({error_code}) for {file_path}, "
            f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
        )
        _retry_or_give_up(self, e, file_path)
    except Exception as e:  # noqa: BLE001 — this is the task's catch-all retry-classification point: boto, the filesystem and the network raise unrelated types, and each must become another attempt or a task failure the chain can see
        # Retry on any other transient failure
        logger.warning(
            f"S3 upload error for {file_path}, "
            f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
        )
        _retry_or_give_up(self, e, file_path)
