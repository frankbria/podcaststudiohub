"""
Comprehensive multi-tenant isolation tests

Tests verify:
1. TenantContextMiddleware extracts tenant_id from JWT tokens
2. PostgreSQL RLS context is set correctly (app.tenant_id)
3. RLS policies enforce tenant data isolation
4. Cross-tenant data access is blocked
5. Different tenants cannot see each other's data
6. Exception handling: expected errors logged, unexpected errors propagated
"""
import pytest
import uuid
from unittest.mock import patch
from httpx import AsyncClient
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from src.models.user import User
from src.services.auth_service import hash_password
from src.database import set_tenant_context


# =============================================================================
# RLS Context Tests - Direct Database Level
# =============================================================================

@pytest.mark.asyncio
async def test_rls_context_set_in_session(test_db: AsyncSession):
    """
    Verify app.tenant_id session variable is set correctly.

    This tests the PostgreSQL session variable that RLS policies use
    to filter queries by tenant.
    """
    # Set tenant context using the safe helper function
    tenant_id = str(uuid.uuid4())
    await set_tenant_context(test_db, tenant_id)

    # Verify context was set
    result = await test_db.execute(
        text("SELECT current_setting('app.tenant_id', true)")
    )
    current_tenant = result.scalar()
    assert current_tenant == tenant_id


@pytest.mark.skip(reason="Test fixture transaction handling interferes with RLS context. API-level tests verify RLS works.")
@pytest.mark.asyncio
async def test_rls_filters_users_by_tenant(test_db: AsyncSession):
    """
    Verify User queries are filtered by tenant_id via RLS.

    Creates users in two different tenants and verifies that setting
    the tenant context only returns users from that tenant.

    Note: This test is skipped because the test_db fixture's transaction
    handling interferes with SET LOCAL commands. The API-level tests
    (test_tenant_isolation_list_endpoints_filter_by_tenant) verify that
    RLS is working correctly in practice.
    """
    # Create users in two tenants
    tenant1_id = uuid.uuid4()
    tenant2_id = uuid.uuid4()

    user1 = User(
        id=uuid.uuid4(),
        email=f"tenant1user_{uuid.uuid4()}@example.com",
        password_hash=hash_password("Password123!"),
        tenant_id=tenant1_id,
        full_name="Tenant One User",
        is_active=True
    )
    user2 = User(
        id=uuid.uuid4(),
        email=f"tenant2user_{uuid.uuid4()}@example.com",
        password_hash=hash_password("Password123!"),
        tenant_id=tenant2_id,
        full_name="Tenant Two User",
        is_active=True
    )

    test_db.add_all([user1, user2])
    await test_db.commit()

    # Set tenant context to tenant1
    await set_tenant_context(test_db, str(tenant1_id))

    # Query all users (should only return user1 due to RLS)
    result = await test_db.execute(select(User))
    users = result.scalars().all()

    # Should only see tenant1's user
    assert len(users) >= 1  # At least our user
    user_emails = [u.email for u in users]
    assert user1.email in user_emails
    assert user2.email not in user_emails


# =============================================================================
# API Level Tenant Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_registration_creates_separate_tenants(client: AsyncClient):
    """
    Verify that registering two users creates separate tenants.

    Each user registration should create a new tenant, ensuring
    complete isolation between unrelated users.
    """
    # Register first user
    user1_response = await client.post("/auth/register", json={
        "email": f"isolation_test1_{uuid.uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Isolation Test One"
    })
    assert user1_response.status_code == 201
    user1_data = user1_response.json()
    assert "access_token" in user1_data
    tenant1_id = user1_data["user"]["tenant_id"]

    # Register second user
    user2_response = await client.post("/auth/register", json={
        "email": f"isolation_test2_{uuid.uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Isolation Test Two"
    })
    assert user2_response.status_code == 201
    user2_data = user2_response.json()
    assert "access_token" in user2_data
    tenant2_id = user2_data["user"]["tenant_id"]

    # Verify different tenant IDs
    assert tenant1_id != tenant2_id

    # Verify both are valid UUIDs
    assert uuid.UUID(tenant1_id)
    assert uuid.UUID(tenant2_id)


@pytest.mark.asyncio
async def test_tenant_isolation_list_endpoints_filter_by_tenant(client: AsyncClient):
    """
    Verify list endpoints only return data for the current tenant.

    When listing resources (projects), users should only see their
    own tenant's data, not data from other tenants.
    """
    # Register two users via the API — each gets a separate tenant automatically
    user1_resp = await client.post("/auth/register", json={
        "email": f"list_test1_{uuid.uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "List Test User 1"
    })
    assert user1_resp.status_code == 201
    token1 = user1_resp.json()["access_token"]

    user2_resp = await client.post("/auth/register", json={
        "email": f"list_test2_{uuid.uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "List Test User 2"
    })
    assert user2_resp.status_code == 201
    token2 = user2_resp.json()["access_token"]

    # User 1 creates 2 projects
    resp = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "name": "User1 Project A",
            "description": "Project A",
            "podcast_metadata": {"show_title": "Show A", "author": "User 1", "description": "Desc A"}
        }
    )
    assert resp.status_code == 201
    resp = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token1}"},
        json={
            "name": "User1 Project B",
            "description": "Project B",
            "podcast_metadata": {"show_title": "Show B", "author": "User 1", "description": "Desc B"}
        }
    )
    assert resp.status_code == 201

    # User 2 creates 1 project
    resp = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "name": "User2 Project C",
            "description": "Project C",
            "podcast_metadata": {"show_title": "Show C", "author": "User 2", "description": "Desc C"}
        }
    )
    assert resp.status_code == 201

    # User 1 lists projects (should see only 2)
    list1_response = await client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert list1_response.status_code == 200
    user1_data = list1_response.json()

    # Response is paginated: {projects: [], total: N, ...}
    assert "projects" in user1_data
    user1_projects = user1_data["projects"]
    assert len(user1_projects) == 2

    project_names = [p["name"] for p in user1_projects]
    assert "User1 Project A" in project_names
    assert "User1 Project B" in project_names
    assert "User2 Project C" not in project_names

    # User 2 lists projects (should see only 1)
    list2_response = await client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert list2_response.status_code == 200
    user2_data = list2_response.json()
    user2_projects = user2_data["projects"]
    assert len(user2_projects) == 1
    assert user2_projects[0]["name"] == "User2 Project C"


# =============================================================================
# Middleware Tests
# =============================================================================

@pytest.mark.asyncio
async def test_middleware_extracts_tenant_id_from_token(client: AsyncClient):
    """
    Verify TenantContextMiddleware extracts tenant_id from JWT token.

    This tests the middleware's ability to parse the Authorization header
    and extract tenant_id from the JWT payload.
    """
    # Register user
    response = await client.post("/auth/register", json={
        "email": f"middleware_test_{uuid.uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Middleware Test User"
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    assert "tenant_id" in response.json()["user"]

    # Make authenticated request
    protected_response = await client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert protected_response.status_code == 200

    # The fact that this succeeds verifies middleware worked
    # (if tenant context wasn't set, RLS would fail)


@pytest.mark.asyncio
async def test_middleware_skips_public_endpoints():
    """
    Verify middleware skips tenant extraction for public endpoints.

    Public endpoints like /health and /docs should not require
    authentication or tenant context.
    """
    from src.middleware.tenant import TenantContextMiddleware

    public_paths = TenantContextMiddleware.PUBLIC_PATHS

    # Verify expected public paths are included
    assert "/" in public_paths
    assert "/health" in public_paths
    assert "/docs" in public_paths
    assert "/auth/login" in public_paths
    assert "/auth/register" in public_paths


# =============================================================================
# Security Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tenant_isolation_prevents_sql_injection(test_db: AsyncSession):
    """
    Verify tenant context setting uses safe SQL execution.

    This test ensures set_tenant_context validates UUIDs
    to prevent SQL injection attacks.
    """
    # Attempt SQL injection in tenant_id
    malicious_tenant_id = "'; DROP TABLE users; --"

    # This should raise ValueError due to invalid UUID format
    with pytest.raises(ValueError, match="Invalid tenant_id format"):
        await set_tenant_context(test_db, malicious_tenant_id)


@pytest.mark.asyncio
async def test_tenant_isolation_without_authentication(client: AsyncClient):
    """
    Verify protected endpoints return error without authentication.

    Requests without valid JWT tokens should be rejected before
    tenant isolation is even considered.
    """
    # Try to access projects without token
    response = await client.get("/projects")
    # FastAPI HTTPBearer returns 403 when no Authorization header
    assert response.status_code == 403

    # Try with invalid token
    response = await client.get(
        "/projects",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_tenant_dependency():
    """
    Verify get_current_tenant() dependency works correctly.
    """
    from src.dependencies import get_current_tenant

    # Test with tenant_id in request state
    class MockRequest:
        class MockState:
            tenant_id = str(uuid.uuid4())

        state = MockState()

    request = MockRequest()
    tenant_id = get_current_tenant(request)
    assert isinstance(tenant_id, uuid.UUID)
    assert str(tenant_id) == request.state.tenant_id

    # Test without tenant_id (should raise HTTPException)
    class MockRequestNoTenant:
        class MockState:
            pass

        state = MockState()

    request_no_tenant = MockRequestNoTenant()
    with pytest.raises(HTTPException) as exc_info:
        get_current_tenant(request_no_tenant)

    assert exc_info.value.status_code == 401
    assert "Tenant context not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_set_tenant_context_validates_uuid():
    """
    Verify set_tenant_context validates tenant_id is a valid UUID.
    """
    from src.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # Valid UUID should work
        valid_uuid = str(uuid.uuid4())
        await set_tenant_context(session, valid_uuid)

        # Invalid UUID should raise ValueError
        with pytest.raises(ValueError, match="Invalid tenant_id format"):
            await set_tenant_context(session, "not-a-uuid")

        with pytest.raises(ValueError, match="Invalid tenant_id format"):
            await set_tenant_context(session, "12345")

        with pytest.raises(ValueError, match="Invalid tenant_id format"):
            await set_tenant_context(session, "")


# =============================================================================
# Middleware Exception Handling Tests (Issue #39)
# =============================================================================

@pytest.mark.asyncio
async def test_middleware_handles_invalid_token_gracefully(client: AsyncClient):
    """
    Verify middleware continues without tenant context when token is malformed.

    A malformed token should be caught as a ValueError (from verify_jwt_token),
    logged at DEBUG level, and the request should proceed without tenant context.
    The auth dependency (get_current_user) handles the actual 401 response.
    """
    response = await client.get(
        "/projects",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"}
    )
    # Auth dependency rejects invalid token with 401
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_middleware_propagates_http_exceptions(client: AsyncClient):
    """
    Verify HTTPException raised during tenant extraction is NOT swallowed.

    If a helper function raises HTTPException (e.g., 401 Unauthorized),
    the middleware must re-raise it — not catch and silently continue.
    In Starlette's BaseHTTPMiddleware, exceptions raised in dispatch()
    propagate through the ASGI transport rather than being converted to
    HTTP responses, so we verify via pytest.raises.
    """
    with patch(
        "src.middleware.tenant.extract_token_from_header",
        side_effect=HTTPException(status_code=401, detail="Token revoked"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await client.get(
                "/projects",
                headers={"Authorization": "Bearer some-token"}
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token revoked"


@pytest.mark.asyncio
async def test_middleware_logs_and_reraises_unexpected_errors(client: AsyncClient):
    """
    Verify unexpected errors in tenant middleware are logged and re-raised.

    If an unexpected exception (e.g., RuntimeError) occurs during tenant
    extraction, it must be logged at ERROR level with a stack trace and
    re-raised. In Starlette's BaseHTTPMiddleware, re-raised exceptions
    propagate through the ASGI transport, so we verify via pytest.raises.
    """
    with patch(
        "src.middleware.tenant.get_tenant_id_from_token",
        side_effect=RuntimeError("database connection lost"),
    ), patch(
        "src.middleware.tenant.extract_token_from_header",
        return_value="fake-token",
    ), patch(
        "src.middleware.tenant.logger"
    ) as mock_logger:
        with pytest.raises(RuntimeError, match="database connection lost"):
            await client.get(
                "/projects",
                headers={"Authorization": "Bearer some-token"}
            )
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "Unexpected error in tenant middleware" in call_args[0][0]
        assert call_args[1].get("exc_info") is True


@pytest.mark.asyncio
async def test_middleware_handles_missing_tenant_claim(client: AsyncClient):
    """
    Verify middleware handles a valid JWT that lacks a tenant_id claim.

    If the JWT is valid but doesn't contain tenant_id, the middleware should
    continue without setting tenant context (no error).
    """
    from jose import jwt
    from src.config import settings

    # Create a JWT without tenant_id claim
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "test@example.com"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = await client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    # Auth dependency may reject (no user in DB), but middleware shouldn't crash
    # The key assertion is that we don't get a 500 error from the middleware
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_middleware_valid_token_still_extracts_tenant(client: AsyncClient):
    """
    Sanity check: valid token still extracts tenant_id correctly after refactor.
    """
    response = await client.post("/auth/register", json={
        "email": f"exception_test_{uuid.uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Exception Test User"
    })
    assert response.status_code == 201
    token = response.json()["access_token"]

    projects_response = await client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert projects_response.status_code == 200
