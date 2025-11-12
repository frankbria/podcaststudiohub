"""
Health check endpoint tests
"""
import pytest
from httpx import AsyncClient


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
