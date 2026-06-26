"""Redis distributed lock for podcast generation idempotency (issue #295).

``generate_podcast_task`` performs paid, non-idempotent LLM/TTS work. The lock
blocks concurrent/duplicate in-flight runs (e.g. a broker-redelivered message or
a double-dispatch) from re-running the paid pipeline, and self-heals after a
crash via TTL expiry so a genuinely failed run can still be retried later.

Mirrors the Redis-access convention in ``services/distribution_target_service.py``
and ``services/rate_limiter.py`` (``Redis.from_url(..., decode_responses=True)``).
"""
import logging

from redis import Redis

from src.config import settings

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "podcast_generation_lock:"

# TTL is set just above the hard task time limit so a lock outlives the longest
# legitimate run, then auto-expires if the worker is killed before release.
_LOCK_TTL_BUFFER_SECONDS = 60

# Atomic compare-and-delete: only release the lock if we still own it, so a lock
# already re-acquired by a later run is never deleted out from under it.
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def _redis() -> Redis:
    """Redis client from settings.REDIS_URL (same instance as rate limiter / OAuth state)."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _lock_key(episode_id: str) -> str:
    return f"{_LOCK_PREFIX}{episode_id}"


def acquire_generation_lock(episode_id: str, task_id: str) -> bool:
    """Acquire the per-episode generation lock.

    Returns True if this task may proceed. Re-entrant: a Celery retry keeps the
    same ``task_id``, so re-acquiring our own lock returns True rather than
    deadlocking the retry. Fail-open on Redis errors so a Redis outage cannot
    permanently block generation.
    """
    key = _lock_key(episode_id)
    ttl = settings.CELERY_TASK_TIME_LIMIT + _LOCK_TTL_BUFFER_SECONDS
    try:
        client = _redis()
        if client.set(key, task_id, nx=True, ex=ttl):
            return True
        # Key already held — only this task's own retry may proceed.
        return client.get(key) == task_id
    except Exception as exc:
        logger.warning(
            "Redis lock acquire failed for episode %s; proceeding without lock "
            "(fail-open): %s",
            episode_id, exc,
        )
        return True


def release_generation_lock(episode_id: str, task_id: str) -> None:
    """Release the lock iff this task still owns it. Fail-open on Redis errors."""
    try:
        _redis().eval(_RELEASE_SCRIPT, 1, _lock_key(episode_id), task_id)
    except Exception as exc:
        logger.warning(
            "Redis lock release failed for episode %s: %s", episode_id, exc
        )
