"""
Celery tasks for audio snippet merging and composition
"""
from celery import Task
from typing import List, Dict, Any, Tuple
import logging
import os
import tempfile

import boto3

from src.worker import celery_app
from src.config import settings
from src.tasks.retry_utils import calculate_backoff

logger = logging.getLogger(__name__)


def _resolve_segment_files(
    timeline: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Materialize S3-backed timeline segments as local tempfiles (issue #376).

    Snippets uploaded with S3 configured exist only as S3 objects, so the
    resolver emits ``{"s3_key": …}`` entries; download each to a tempfile with
    sync boto3 (consistent with ``upload_to_s3_task``) so pydub can read it.
    A failed download skips just that segment (log, don't fail the chain) —
    worst case the merge degrades to the generated audio alone. Segments with
    a ``file_path`` pass through untouched, including a missing main file,
    which must still fail loudly in the merge loop.

    Returns ``(segments, temp_paths)``; the caller must delete ``temp_paths``
    after the merge (success and failure paths). Failed downloads' tempfiles
    are also returned so one cleanup site covers everything.
    """
    resolved: List[Dict[str, Any]] = []
    temp_paths: List[str] = []
    s3_client = None
    for segment in timeline:
        s3_key = segment.get("s3_key")
        if segment.get("file_path") or not s3_key:
            resolved.append(segment)
            continue
        try:
            fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(s3_key)[1] or ".mp3")
            os.close(fd)
            temp_paths.append(tmp)
            if s3_client is None:
                s3_client = boto3.client("s3")
            s3_client.download_file(settings.AWS_S3_BUCKET, s3_key, tmp)
        except Exception as exc:
            logger.warning(
                "Composition: skipping %s segment — download of s3://%s/%s "
                "failed: %s",
                segment.get("segment_type"), settings.AWS_S3_BUCKET, s3_key, exc,
            )
            continue
        resolved.append({**segment, "file_path": tmp})
    return resolved, temp_paths


@celery_app.task(bind=True, name="merge_audio_snippets", time_limit=300, max_retries=2)
def merge_audio_snippets_task(
    self: Task,
    episode_id: str,
    timeline: List[Dict[str, Any]],
    output_path: str
) -> Dict[str, Any]:
    """
    Merge audio snippets according to the composition timeline.

    Uses PyDub and FFmpeg to merge audio files with normalization.

    Args:
        self: Celery task instance
        episode_id: UUID of the episode
        timeline: List of timeline segments with audio file paths and positions
        output_path: Path for the final composed audio file

    Returns:
        Dictionary with composition results

    Raises:
        ValueError: If the timeline is empty — composing would export a
            zero-length silent file that then replaces the generated audio
            at upload (issue #313). Raised outside the retry handler because
            an empty timeline is deterministic; the chain's link_error
            callback marks the episode failed.
    """
    if not timeline:
        raise ValueError(
            f"Composition timeline for episode {episode_id} is empty; "
            "at least one segment (the generated audio) is required"
        )

    temp_paths: List[str] = []
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'episode_id': episode_id,
                'progress': 0,
                'status': 'Starting audio composition...'
            }
        )

        # Download S3-backed segments to worker tempfiles (issue #376).
        timeline, temp_paths = _resolve_segment_files(timeline)

        from pydub import AudioSegment

        # Initialize empty audio
        final_audio = AudioSegment.empty()

        # Process timeline segments
        total_segments = len(timeline)
        for idx, segment in enumerate(timeline):
            progress = int((idx / total_segments) * 100)
            self.update_state(
                state='PROGRESS',
                meta={
                    'episode_id': episode_id,
                    'progress': progress,
                    'status': f'Merging segment {idx + 1}/{total_segments}...'
                }
            )

            # Load audio file
            audio_file = segment['file_path']
            audio = AudioSegment.from_file(audio_file)

            # Apply normalization if specified
            if segment.get('normalize', False):
                audio = audio.normalize()

            # Apply fade in/out if specified
            if segment.get('fade_in_ms'):
                audio = audio.fade_in(segment['fade_in_ms'])
            if segment.get('fade_out_ms'):
                audio = audio.fade_out(segment['fade_out_ms'])

            # Append to final audio
            final_audio += audio

        # Export final composed audio
        final_audio.export(output_path, format="mp3", bitrate="192k")

        file_size_bytes = os.path.getsize(output_path)
        duration_seconds = len(final_audio) / 1000.0

        return {
            "status": "success",
            "output_path": output_path,
            "duration_seconds": duration_seconds,
            "file_size_bytes": file_size_bytes,
            "error": None
        }

    except Exception as e:
        logger.warning(
            f"Audio composition error for episode {episode_id}, "
            f"attempt {self.request.retries + 1}/{self.max_retries + 1}: {e}"
        )
        try:
            raise self.retry(exc=e, countdown=calculate_backoff(self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(
                f"Audio composition failed after {self.max_retries} retries "
                f"for episode {episode_id}: {e}"
            )
            return {
                "status": "failed",
                "output_path": None,
                "duration_seconds": 0,
                "file_size_bytes": 0,
                "error": str(e)
            }
    finally:
        # Downloaded snippet tempfiles are per-attempt artifacts: remove them on
        # success, failure, AND the retry path (the next attempt re-downloads).
        for tmp in temp_paths:
            try:
                os.remove(tmp)
            except OSError:
                pass
