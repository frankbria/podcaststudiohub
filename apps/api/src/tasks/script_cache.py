"""Keep a generation's paid script, and its sources, across Celery retries (#620).

``generate_podcast_task`` buys the script (LLM) before voicing it (TTS) and
storing it (S3). A failure in either later step retries the whole task body,
which would buy the script again. A retry keeps the Celery task id and a
regeneration is dispatched under a new one, so the task id is exactly the
scope of "this generation": a retry reuses the script, a regeneration never
does.

The extracted sources are kept with it: a retry that fetched its URLs again
could fail on a site that has since gone down, or screen the cached script
against text that changed after the script was written from it.

Fail-open like the generation lock in ``idempotency.py``: the cache saves money,
so a Redis outage or an unreadable entry costs a regenerated script, nothing
more.
"""
import logging
from typing import List, Optional, Tuple

from pydantic import BaseModel, ValidationError
from redis import Redis
from redis.exceptions import RedisError

from src.config import settings
from src.engine.models import Script

logger = logging.getLogger(__name__)

_PREFIX = "podcast_generation_script:"
# Bounded so an unresponsive (not just unreachable) Redis fails open quickly
# instead of holding the task until its hard time limit.
_SOCKET_TIMEOUT_SECONDS = 5


class _CachedRun(BaseModel):
    script: Script
    sources: List[str]


def _key(task_id: str) -> str:
    return f"{_PREFIX}{task_id}"


def _redis() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
    )


def load_run(task_id: str) -> Optional[Tuple[Script, List[str]]]:
    """The script this generation already paid for and its sources, or None."""
    try:
        cached = _redis().get(_key(task_id))
    except (RedisError, OSError) as exc:
        logger.warning("Script cache read failed for task %s; regenerating: %s", task_id, exc)
        return None
    if cached is None:
        return None
    try:
        run = _CachedRun.model_validate_json(cached)
    except ValidationError as exc:
        logger.warning("Ignoring an unreadable cached script for task %s: %s", task_id, exc)
        return None
    return run.script, run.sources


def save_run(task_id: str, script: Script, sources: List[str], ttl_seconds: int) -> None:
    """Keep ``script`` and its ``sources`` for this generation's retries."""
    payload = _CachedRun(script=script, sources=sources).model_dump_json()
    try:
        _redis().set(_key(task_id), payload, ex=ttl_seconds)
    except (RedisError, OSError) as exc:
        logger.warning("Script cache write failed for task %s: %s", task_id, exc)
