"""
Unit tests for the SSE authentication dependency (get_current_user_from_query).

GAP-005: EventSource API cannot send custom headers, so JWT tokens must be
accepted via query parameters for SSE endpoints.

These tests run without a database by testing the dependency logic in isolation.
"""
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import timedelta

from src.middleware.auth import get_current_user_from_query
from src.services.auth_service import create_jwt_token, verify_jwt_token


# =============================================================================
# Signature / Interface Tests
# =============================================================================

def test_get_current_user_from_query_exists():
    """Dependency function must exist in middleware.auth."""
    from src.middleware import auth
    assert hasattr(auth, "get_current_user_from_query"), (
        "get_current_user_from_query must be defined in middleware.auth"
    )


def test_get_current_user_from_query_is_async():
    """SSE auth dependency must be a coroutine function."""
    import asyncio
    assert asyncio.iscoroutinefunction(get_current_user_from_query), (
        "get_current_user_from_query must be an async function"
    )


def test_get_current_user_from_query_accepts_token_param():
    """Dependency must accept 'token' query parameter."""
    sig = inspect.signature(get_current_user_from_query)
    assert "token" in sig.parameters, (
        "get_current_user_from_query must accept a 'token' parameter for SSE auth"
    )


def test_get_current_user_from_query_token_defaults_none():
    """The 'token' parameter must default to None (optional query param)."""
    sig = inspect.signature(get_current_user_from_query)
    token_param = sig.parameters["token"]
    # The default should be None (from fastapi.Query(None))
    assert token_param.default is not inspect.Parameter.empty, (
        "token parameter must have a default value (None) so it's optional"
    )


def test_get_current_user_from_query_accepts_request_param():
    """Dependency must accept 'request' parameter to fall back on Authorization header."""
    sig = inspect.signature(get_current_user_from_query)
    assert "request" in sig.parameters, (
        "get_current_user_from_query must accept 'request' to check Authorization header"
    )


def test_get_current_user_from_query_accepts_db_param():
    """Dependency must accept 'db' parameter for database access."""
    sig = inspect.signature(get_current_user_from_query)
    assert "db" in sig.parameters, (
        "get_current_user_from_query must accept 'db' for user lookup"
    )


# =============================================================================
# JWT Token Verification Tests (no database)
# =============================================================================

def test_verify_jwt_token_valid():
    """JWT tokens created by create_jwt_token must be verifiable."""
    user_id = uuid4()
    tenant_id = uuid4()
    token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="test@example.com"
    )
    payload = verify_jwt_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)


def test_verify_jwt_token_expired_raises():
    """Expired tokens must raise ValueError."""
    user_id = uuid4()
    tenant_id = uuid4()
    expired_token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="test@example.com",
        expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(ValueError, match="Invalid token"):
        verify_jwt_token(expired_token)


def test_verify_jwt_token_invalid_raises():
    """Invalid tokens must raise ValueError."""
    with pytest.raises(ValueError, match="Invalid token"):
        verify_jwt_token("invalid.token.string")


# =============================================================================
# Dependency Behavior Tests (mocked database)
# =============================================================================

@pytest.mark.asyncio
async def test_get_current_user_from_query_with_valid_token():
    """Dependency must return user when valid token provided as query param."""
    user_id = uuid4()
    tenant_id = uuid4()

    # Create a real JWT token
    token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="sse@example.com"
    )

    # Mock database and user
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.tenant_id = tenant_id
    mock_user.is_active = True

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    result = await get_current_user_from_query(
        token=token,
        request=None,
        db=mock_db
    )
    assert result == mock_user
    assert hasattr(result, "_tenant_id_from_token")


@pytest.mark.asyncio
async def test_get_current_user_from_query_no_token_raises_401():
    """Dependency must raise HTTP 401 when no token provided."""
    from fastapi import HTTPException

    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_from_query(
            token=None,
            request=None,
            db=mock_db
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_from_query_invalid_token_raises_401():
    """Dependency must raise HTTP 401 for invalid token."""
    from fastapi import HTTPException

    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_from_query(
            token="invalid.jwt.token",
            request=None,
            db=mock_db
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_from_query_expired_token_raises_401():
    """Dependency must raise HTTP 401 for expired token."""
    from fastapi import HTTPException

    user_id = uuid4()
    tenant_id = uuid4()
    expired_token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="expired@example.com",
        expires_delta=timedelta(seconds=-1)
    )

    mock_db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_from_query(
            token=expired_token,
            request=None,
            db=mock_db
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_from_query_user_not_found_raises_401():
    """Dependency must raise HTTP 401 when user not found in database."""
    from fastapi import HTTPException

    user_id = uuid4()
    tenant_id = uuid4()
    token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="notfound@example.com"
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # User not found
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_from_query(
            token=token,
            request=None,
            db=mock_db
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_from_query_inactive_user_raises_403():
    """Dependency must raise HTTP 403 for inactive user."""
    from fastapi import HTTPException

    user_id = uuid4()
    tenant_id = uuid4()
    token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="inactive@example.com"
    )

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.is_active = False  # Inactive user

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_from_query(
            token=token,
            request=None,
            db=mock_db
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_from_query_falls_back_to_header():
    """When no query token, dependency must check Authorization header."""
    user_id = uuid4()
    tenant_id = uuid4()
    token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="header@example.com"
    )

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.tenant_id = tenant_id
    mock_user.is_active = True

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    # Mock request with Authorization header
    mock_request = MagicMock()
    mock_request.headers.get.return_value = f"Bearer {token}"

    result = await get_current_user_from_query(
        token=None,  # No query param token
        request=mock_request,
        db=mock_db
    )
    assert result == mock_user


@pytest.mark.asyncio
async def test_get_current_user_from_query_prefers_query_over_header():
    """When both query token and header token present, query token should be used."""
    user_id = uuid4()
    tenant_id = uuid4()
    query_token = create_jwt_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="query@example.com"
    )

    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.tenant_id = tenant_id
    mock_user.is_active = True

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    # Mock request with different Authorization header token
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer some-other-token"

    # Should succeed using query token, not the (invalid) header token
    result = await get_current_user_from_query(
        token=query_token,  # Query param token takes precedence
        request=mock_request,
        db=mock_db
    )
    assert result == mock_user
    # Database should not have been called with the header token
    # (it was called once with the query token's user_id)
    mock_db.execute.assert_called_once()


# =============================================================================
# Generation Router: Endpoint Signature Tests
# =============================================================================

def test_progress_endpoint_uses_sse_auth_dependency():
    """The SSE progress endpoint must use get_current_user_from_query, not get_current_user."""
    import inspect
    from src.routers.generation import get_generation_progress_stream

    sig = inspect.signature(get_generation_progress_stream)
    params = sig.parameters

    # The endpoint should have current_user parameter
    assert "current_user" in params, "SSE endpoint must have current_user parameter"

    # Verify the dependency is the SSE-compatible one (not header-only)
    current_user_param = params["current_user"]
    default = current_user_param.default

    # The default should be a Depends(get_current_user_from_query)
    # Check by looking at the dependency's function
    if hasattr(default, "dependency"):
        assert default.dependency == get_current_user_from_query, (
            "SSE endpoint must use get_current_user_from_query dependency, not get_current_user"
        )
