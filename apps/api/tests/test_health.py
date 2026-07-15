"""
Health check endpoint tests

/health is the LIVENESS probe (static — is the process up?) and /ready is the
READINESS probe (does it have a working DB + Redis?). The split matters: a
dependency outage must fail /ready so the gate drains traffic, while /health
stays 200 so a supervisor doesn't restart-loop a healthy process (issue #320).
"""
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from src.middleware.tenant import TenantContextMiddleware


@pytest.fixture(autouse=True)
async def dispose_readiness_engine():
    """Drop the readiness probe's pooled connections between tests.

    /ready checks the app's real module-global engine (that is the point — it
    proves the pool the app actually serves from is usable). That engine's pool
    caches connections bound to the event loop that opened them, and
    pytest-asyncio gives every test a fresh loop, so a connection pooled by one
    test would be checked out on a dead loop by the next ("got Future attached
    to a different loop"). Production never hits this — uvicorn runs one loop for
    the process lifetime — so dispose here rather than weaken the probe.
    """
    yield
    from src.database import engine

    await engine.dispose()


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """
    Test the /health endpoint returns healthy status
    """
    response = await client.get("/health")

    # Assert HTTP 200 response status
    assert response.status_code == 200

    # Assert response JSON structure
    data = response.json()
    assert "status" in data
    assert "version" in data

    # Assert expected values
    assert data["status"] == "healthy"
    assert isinstance(data["version"], str)


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """
    Test the root endpoint returns API information
    """
    response = await client.get("/")

    # Assert HTTP 200 response status
    assert response.status_code == 200

    # Assert response JSON structure
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "docs" in data

    # Assert expected values
    assert data["message"] == "Podcastfy API"
    assert data["docs"] == "/docs"


@pytest.mark.asyncio
async def test_ready_endpoint_reports_dependency_checks(client: AsyncClient):
    """/ready round-trips the real DB and Redis.

    Needs a live Redis at REDIS_URL as well as the test Postgres — deliberately
    unmocked, per the repo's real-services rule, since a probe that only ever
    PINGs a mock proves nothing. CI provisions both as service containers.
    """
    response = await client.get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"] == {"database": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_ready_returns_503_when_database_is_down(client: AsyncClient):
    with patch("src.main._check_database", side_effect=OSError("connection refused")):
        response = await client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"] == "error"
    # Redis is independently healthy — the probe must say which one broke.
    assert data["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_redis_is_down(client: AsyncClient):
    with patch("src.main._check_redis", side_effect=OSError("connection refused")):
        response = await client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["checks"]["redis"] == "error"
    assert data["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_dependency_hangs(client: AsyncClient):
    """A hung dependency must fail the probe fast, not hang it."""
    import asyncio

    async def _hang():
        await asyncio.sleep(30)

    with patch("src.main._check_redis", side_effect=_hang), \
            patch("src.main.settings.READINESS_CHECK_TIMEOUT_SECONDS", 0.05):
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"


@pytest.mark.asyncio
async def test_ready_does_not_leak_dependency_error_details(client: AsyncClient):
    """/ready is unauthenticated; connection errors quote DSNs and hostnames."""
    with patch(
        "src.main._check_database",
        side_effect=OSError("could not connect to host=10.0.0.5 user=podcastfy_app"),
    ):
        response = await client.get("/ready")

    assert "10.0.0.5" not in response.text
    assert "podcastfy_app" not in response.text


@pytest.mark.asyncio
async def test_health_stays_up_when_dependencies_are_down(client: AsyncClient):
    """Liveness must not collapse into readiness."""
    with patch("src.main._check_database", side_effect=OSError("down")), \
            patch("src.main._check_redis", side_effect=OSError("down")):
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready_is_a_public_path():
    """Otherwise the probe gets metered and tenant-resolved on every poll."""
    assert "/ready" in TenantContextMiddleware.PUBLIC_PATHS


@pytest.mark.asyncio
async def test_404_handler(client: AsyncClient):
    """
    Test the custom 404 error handler
    """
    response = await client.get("/nonexistent-endpoint")

    # Assert HTTP 404 response status
    assert response.status_code == 404

    # Assert response JSON structure
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Endpoint not found"
