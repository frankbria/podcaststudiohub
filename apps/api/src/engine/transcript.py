"""Durable storage for a generated ``Script`` (issue #541).

``episodes.transcript_path`` has been ``NULL`` for every episode ever generated:
podcastfy wrote its transcript into the per-run temp dir, which
``_cleanup_temp_file`` removes wholesale along with the audio (#309). The
script was never anything but a disposable intermediate.

Owning the script layer makes it an artifact worth keeping, so it is stored
beside the audio under the same tenant prefix. #543 wires the returned path into
``episodes.transcript_path``.
"""
import logging
import os
import uuid

import boto3

from src.config import settings
from src.engine.llm import EngineError
from src.engine.models import Script

logger = logging.getLogger(__name__)


def _checked_id(label: str, value: str) -> str:
    """Reject anything that is not a UUID before it reaches a path.

    Both ids come from UUID primary keys, so this is cheap. It matters because
    the local-storage branch below is a real filesystem join, where ``..`` is
    honoured and an absolute second component replaces the first — unlike the
    S3 key, where neither has any meaning. Validating here keeps a future
    caller from turning the no-S3 dev path (#292) into an arbitrary write.
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise EngineError(f"{label} is not a valid UUID: {value!r}") from exc
    return str(value)


def build_transcript_s3_key(user_id: str, episode_id: str) -> str:
    """Canonical S3 key for an episode's transcript.

    Deliberately the same layout as ``build_podcast_s3_key`` so the transcript
    lands under the ``podcasts/user-*/`` prefix that bucket policy, IAM and
    lifecycle rules scope on (#215).
    """
    return (
        f"podcasts/user-{_checked_id('user_id', user_id)}"
        f"/episode-{_checked_id('episode_id', episode_id)}.transcript.json"
    )


def persist_transcript(script: Script, user_id: str, episode_id: str) -> str:
    """Store ``script`` as JSON and return where it went.

    Returns the S3 key when a bucket is configured, otherwise the local path.
    Mirrors the audio path's no-S3 fallback (#292), so a dev or single-box
    deployment keeps its transcripts instead of writing them to /tmp.
    """
    user_id = _checked_id("user_id", user_id)
    episode_id = _checked_id("episode_id", episode_id)
    body = script.model_dump_json(indent=2)

    if settings.AWS_S3_BUCKET:
        key = build_transcript_s3_key(user_id, episode_id)
        boto3.client("s3", region_name=settings.AWS_REGION).put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Stored transcript for episode %s at s3://%s/%s",
                    episode_id, settings.AWS_S3_BUCKET, key)
        return key

    os.makedirs(settings.LOCAL_AUDIO_STORAGE_PATH, exist_ok=True)
    path = os.path.join(
        settings.LOCAL_AUDIO_STORAGE_PATH, f"episode-{episode_id}.transcript.json"
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    logger.info("Stored transcript for episode %s at %s", episode_id, path)
    return path
