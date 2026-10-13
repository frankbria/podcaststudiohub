"""Keep a generation's paid script across its Celery retries (#620).

``generate_podcast_task`` buys the script (LLM) before voicing it (TTS) and
storing it (S3). A failure in either later step retries the whole task body,
which would buy the script again. A retry keeps the Celery task id and a
regeneration is dispatched under a new one, so the task id is exactly the
scope of "this generation": a retry reuses the script, a regeneration never
does.

Fail-open like the generation lock in ``idempotency.py``: the cache saves money,
so a Redis outage or an unreadable entry costs a regenerated script, nothing
more.
"""
import logging
from typing import Optional

from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError

from src.config import settings
from src.engine.models import Script

logger = logging.getLogger(__name__)

_PREFIX = "podcast_generation_script:"


def _key(task_id: str) -> str:
    return f"{_PREFIX}{task_id}"


def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def load_script(task_id: str) -> Optional[Script]:
    """The script this generation already paid for, or None."""
    try:
        cached = _redis().get(_key(task_id))
    except (RedisError, OSError) as exc:
        logger.warning("Script cache read failed for task %s; regenerating: %s", task_id, exc)
        return None
    if cached is None:
        return None
    try:
        return Script.model_validate_json(cached)
    except ValidationError as exc:
        logger.warning("Ignoring an unreadable cached script for task %s: %s", task_id, exc)
        return None


def save_script(task_id: str, script: Script, ttl_seconds: int) -> None:
    """Keep ``script`` for this generation's retries."""
    try:
        _redis().set(_key(task_id), script.model_dump_json(), ex=ttl_seconds)
    except (RedisError, OSError) as exc:
        logger.warning("Script cache write failed for task %s: %s", task_id, exc)
