"""The paid script survives a Celery retry of the same generation (#620).

Real Redis, as the task uses it; an unreachable Redis is a real closed port.
"""
from uuid import uuid4

import pytest
from redis import Redis

from src.config import settings
from src.engine.models import Script
from src.tasks import script_cache

SCRIPT = Script(
    title="Grounding",
    summary="Two hosts on retrieval.",
    turns=[{"speaker": "host", "text": "Welcome back."}, {"speaker": "guest", "text": "Hi."}],
)
SOURCES = ["Pasted notes.", "Fetched page text."]


@pytest.fixture
def task_id():
    task_id = f"test-{uuid4()}"
    redis = Redis.from_url(settings.REDIS_URL)  # before any test repoints the URL
    yield task_id
    redis.delete(script_cache._key(task_id))


def test_a_saved_script_and_its_sources_are_loaded_back_for_the_same_generation(task_id):
    script_cache.save_run(task_id, SCRIPT, SOURCES, ttl_seconds=60)

    assert script_cache.load_run(task_id) == (SCRIPT, SOURCES)


def test_another_generation_never_sees_it(task_id):
    """A regeneration is dispatched under a new task id; it must buy a fresh
    script for its own sources and config."""
    script_cache.save_run(task_id, SCRIPT, SOURCES, ttl_seconds=60)

    assert script_cache.load_run(f"test-{uuid4()}") is None


def test_the_entry_expires(task_id):
    script_cache.save_run(task_id, SCRIPT, SOURCES, ttl_seconds=60)

    assert 0 < Redis.from_url(settings.REDIS_URL).ttl(script_cache._key(task_id)) <= 60


def test_an_unreachable_redis_only_costs_a_regenerated_script(monkeypatch, task_id):
    """Fail open: the cache saves money, it never blocks a generation."""
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")

    script_cache.save_run(task_id, SCRIPT, SOURCES, ttl_seconds=60)
    assert script_cache.load_run(task_id) is None


def test_an_unreadable_entry_is_ignored(task_id):
    Redis.from_url(settings.REDIS_URL).set(script_cache._key(task_id), "{not json", ex=60)

    assert script_cache.load_run(task_id) is None
