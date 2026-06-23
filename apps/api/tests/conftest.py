"""
Pytest configuration and shared fixtures
"""
import os
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Disable rate limiting for all tests — the limiter uses Redis and would
# throttle the many registration/login calls made across the test suite.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from src.main import app
from src.database import get_db, get_streaming_session_factory


# Test database URL (use PostgreSQL test database)
# Must use the non-superuser podcastfy_app role so that FORCE ROW LEVEL SECURITY
# is respected and tenant isolation tests are meaningful.
# The podcastfy_app role is provisioned by migration 003_force_rls.py.
# Override with TEST_DATABASE_URL env var if needed (e.g. different port).
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://podcastfy_app:podcastfy_app_password@localhost:5432/podcastfy",
)


@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for the test session
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db():
    """
    Create a fresh test database session for each test function.
    Uses transaction rollback for cleanup to keep tests isolated and fast.
    """
    # Create async engine
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False
    )

    # Create session factory
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    # Start a connection and transaction
    async with engine.connect() as conn:
        # Begin transaction
        await conn.begin()

        # Create session bound to this transaction
        async with async_session(bind=conn) as session:
            # Use nested transaction for test isolation
            await session.begin_nested()

            yield session

            # Rollback the nested transaction after test
            await session.rollback()

    await engine.dispose()


@pytest.fixture
def set_system_fields(test_db):
    """Return an async helper that sets pipeline-managed (system) episode fields
    directly in the DB — the same path the generation pipeline uses
    (episode_service.set_episode_system_fields).

    The public PUT endpoint intentionally refuses system fields
    (generation_status, generation_progress, s3_key, duration_seconds, …), so
    tests that need an episode in a particular generated state set them here
    instead of through the API. Relies on the RLS tenant context already
    established on the shared test session by a preceding API request.

    Usage:
        await set_system_fields(episode_id, generation_status="complete", s3_key="…")
    """
    from uuid import UUID
    from src.services.episode_service import (
        get_episode_by_id,
        set_episode_system_fields,
    )

    async def _set(episode_id, **fields):
        episode = await get_episode_by_id(test_db, UUID(str(episode_id)))
        await set_episode_system_fields(test_db, episode, **fields)
        return episode

    return _set


@pytest.fixture
async def client(test_db):
    """
    Create an async HTTP client for testing FastAPI endpoints with test database.
    This fixture properly handles tenant context for RLS by accepting the Request parameter.
    """
    from fastapi import Request
    from src.database import set_tenant_context

    # Override the database dependency with proper tenant context support
    async def override_get_db(request: Request):
        """Override get_db to use test database with tenant context."""
        try:
            # Set tenant context for RLS if available
            if hasattr(request.state, 'tenant_id') and request.state.tenant_id:
                await set_tenant_context(test_db, str(request.state.tenant_id))

            yield test_db
        except Exception:
            await test_db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    # The SSE generator opens a session per poll via get_streaming_session_factory.
    # Bind it to the test session so it (a) sees the test's uncommitted data and
    # (b) never opens connections on the module-global engine, which would leak
    # asyncpg pools across pytest's per-test event loops (issue #220).
    class _TestSessionCM:
        async def __aenter__(self) -> AsyncSession:
            return test_db

        async def __aexit__(
            self,
            exc_type: "type[BaseException] | None",
            exc_val: "BaseException | None",
            exc_tb: object,
        ) -> bool:
            return False

    app.dependency_overrides[get_streaming_session_factory] = lambda: (lambda: _TestSessionCM())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up dependency override
    app.dependency_overrides.clear()
