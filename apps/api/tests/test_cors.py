"""
CORS configuration tests - GAP-034
Verifies that CORS middleware is configured with explicit, restricted permissions.
"""
import pytest
from httpx import AsyncClient

from src.config import settings


@pytest.mark.asyncio
async def test_cors_config_methods_not_wildcard():
    """CORS_ALLOW_METHODS should not use wildcard ['*']"""
    assert settings.CORS_ALLOW_METHODS != ["*"], (
        "CORS_ALLOW_METHODS must be an explicit list, not wildcard"
    )


@pytest.mark.asyncio
async def test_cors_config_headers_not_wildcard():
    """CORS_ALLOW_HEADERS should not use wildcard ['*']"""
    assert settings.CORS_ALLOW_HEADERS != ["*"], (
        "CORS_ALLOW_HEADERS must be an explicit list, not wildcard"
    )


@pytest.mark.asyncio
async def test_cors_config_allows_required_methods():
    """CORS_ALLOW_METHODS should include required HTTP methods"""
    required_methods = {"GET", "POST", "PUT", "DELETE"}
    configured = {m.upper() for m in settings.CORS_ALLOW_METHODS}
    missing = required_methods - configured
    assert not missing, f"Required CORS methods missing: {missing}"


@pytest.mark.asyncio
async def test_cors_config_allows_authorization_header():
    """CORS_ALLOW_HEADERS should include Authorization for JWT support"""
    configured = {h.lower() for h in settings.CORS_ALLOW_HEADERS}
    assert "authorization" in configured, (
        "Authorization header must be explicitly allowed for JWT authentication"
    )


@pytest.mark.asyncio
async def test_cors_config_allows_content_type_header():
    """CORS_ALLOW_HEADERS should include Content-Type"""
    configured = {h.lower() for h in settings.CORS_ALLOW_HEADERS}
    assert "content-type" in configured, (
        "Content-Type header must be explicitly allowed"
    )


@pytest.mark.asyncio
async def test_cors_preflight_response(client: AsyncClient):
    """OPTIONS preflight request should return correct CORS headers"""
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        }
    )
    # CORS preflight responses are 200 or 204
    assert response.status_code in (200, 204)
    # Should include CORS headers
    assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
async def test_cors_allowed_origin_in_response(client: AsyncClient):
    """Requests from allowed origin should include CORS headers"""
    response = await client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_blocks_unauthorized_origin(client: AsyncClient):
    """Requests from unauthorized origin should not receive CORS allow header"""
    response = await client.get(
        "/health",
        headers={"Origin": "http://evil.example.com"}
    )
    # The request will return 200 (server processes it), but CORS header should be absent
    # or not match the evil origin
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin != "http://evil.example.com", (
        "Unauthorized origin should not be reflected in Access-Control-Allow-Origin"
    )


@pytest.mark.asyncio
async def test_cors_excludes_trace_method():
    """CORS should not allow TRACE method"""
    configured = {m.upper() for m in settings.CORS_ALLOW_METHODS}
    assert "TRACE" not in configured, "TRACE method should not be allowed"


@pytest.mark.asyncio
async def test_cors_excludes_connect_method():
    """CORS should not allow CONNECT method"""
    configured = {m.upper() for m in settings.CORS_ALLOW_METHODS}
    assert "CONNECT" not in configured, "CONNECT method should not be allowed"
