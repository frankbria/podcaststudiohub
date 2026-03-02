"""
Pytest configuration and shared fixtures
"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.main import app
from src.database import Base, get_db
from src.config import settings


# Test database URL (use PostgreSQL test database)
# Must use the non-superuser podcastfy_app role so that FORCE ROW LEVEL SECURITY
# is respected and tenant isolation tests are meaningful.
# The podcastfy_app role is provisioned by migration 003_force_rls.py.
TEST_DATABASE_URL = "postgresql+asyncpg://podcastfy_app:podcastfy_app_password@localhost:5432/podcastfy"


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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up dependency override
    app.dependency_overrides.clear()
