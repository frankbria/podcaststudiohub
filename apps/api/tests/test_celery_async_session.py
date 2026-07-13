"""
Regression test for the Celery sync→async DB bridge (issue #382 review).

Celery tasks run async services via ``asyncio.run()``, which destroys its
event loop on return. With the shared pooled engine, a connection checked
back into the pool stays bound to that dead loop and the next ``asyncio.run()``
in the same worker process fails on checkout with "got Future attached to a
different loop" (empirically: every other call). ``celery_async_session``
must therefore survive arbitrarily many sequential event loops.
"""
import asyncio

from sqlalchemy import text

from src.database import celery_async_session


def test_celery_async_session_survives_sequential_event_loops():
    """Three asyncio.run() calls in one process must all reach the DB."""

    async def query() -> int:
        async with celery_async_session() as db:
            result = await db.execute(text("SELECT 1"))
            return result.scalar()

    assert [asyncio.run(query()) for _ in range(3)] == [1, 1, 1]
