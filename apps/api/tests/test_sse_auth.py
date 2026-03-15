"""
Tests for SSE (Server-Sent Events) authentication via query parameter token.

GAP-005: EventSource API cannot send custom headers, so JWT tokens must be
accepted via query parameters for SSE endpoints.
"""
import pytest
from uuid import uuid4, UUID as PyUUID
from datetime import timedelta
from sqlalchemy import update

from src.services.auth_service import create_jwt_token
from src.models.episode import Episode


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def registered_user(client):
    """Create a registered user and return (token, headers, user_id)."""
    email = f"test_{uuid4()}@example.com"
    response = await client.post("/auth/register", json={
        "email": email,
        "password": "SecurePass123!",
        "full_name": "SSE Test User"
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return token, headers


@pytest.fixture
async def episode_with_user(client, registered_user):
    """Create a project and episode, return (episode_id, token, headers)."""
    token, headers = registered_user

    # Create project
    proj_response = await client.post("/projects", headers=headers, json={
        "name": "SSE Test Project",
        "podcast_metadata": {
            "show_title": "SSE Test Show",
            "author": "Test Author",
            "description": "Test Description"
        }
    })
    assert proj_response.status_code == 201
    project_id = proj_response.json()["id"]

    # Create episode
    ep_response = await client.post("/episodes", headers=headers, json={
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {
            "title": "SSE Test Episode",
            "description": "Test episode for SSE auth"
        }
    })
    assert ep_response.status_code == 201
    episode_id = ep_response.json()["id"]

    return episode_id, token, headers


# =============================================================================
# Tests: SSE Progress Endpoint Authentication
# =============================================================================

@pytest.mark.asyncio
async def test_progress_stream_with_query_token(client, episode_with_user, test_db):
    """Test that SSE endpoint accepts JWT token in query parameter."""
    episode_id, token, _ = episode_with_user

    # Set episode to "complete" so the SSE stream terminates after one event.
    # Without this, the endpoint loops forever (while True / sleep 2s) and the
    # test hangs because httpx reads the full response body.
    await test_db.execute(
        update(Episode).where(Episode.id == PyUUID(episode_id)).values(generation_status="complete")
    )
    await test_db.flush()

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress?token={token}"
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_progress_stream_with_header_token(client, episode_with_user, test_db):
    """Test that SSE endpoint still accepts JWT token in Authorization header (backward compat)."""
    episode_id, token, headers = episode_with_user

    await test_db.execute(
        update(Episode).where(Episode.id == PyUUID(episode_id)).values(generation_status="complete")
    )
    await test_db.flush()

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress",
        headers=headers
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_progress_stream_without_token(client, episode_with_user):
    """Test that SSE endpoint returns 401 when no token provided."""
    episode_id, _, _ = episode_with_user

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_with_invalid_token(client, episode_with_user):
    """Test that SSE endpoint returns 401 for invalid token."""
    episode_id, _, _ = episode_with_user

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress?token=invalid.token.here"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_with_expired_token(client, episode_with_user, test_db):
    """Test that SSE endpoint returns 401 for expired token."""
    episode_id, _, _ = episode_with_user

    # Create a token that is already expired
    from src.models.user import User
    from sqlalchemy import select
    result = await test_db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()

    if user:
        expired_token = create_jwt_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        response = await client.get(
            f"/generation/episodes/{episode_id}/progress?token={expired_token}"
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_tenant_isolation(client, episode_with_user):
    """Test that a user cannot access another user's episode progress stream."""
    episode_id, _, _ = episode_with_user

    # Register a second user
    second_user_response = await client.post("/auth/register", json={
        "email": f"other_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Other User"
    })
    assert second_user_response.status_code == 201
    other_token = second_user_response.json()["access_token"]

    # Second user should not be able to access first user's episode
    response = await client.get(
        f"/generation/episodes/{episode_id}/progress?token={other_token}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_progress_stream_nonexistent_episode(client, registered_user):
    """Test that SSE endpoint returns 404 for non-existent episode."""
    token, _ = registered_user
    fake_episode_id = uuid4()

    response = await client.get(
        f"/generation/episodes/{fake_episode_id}/progress?token={token}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_progress_stream_query_token_takes_precedence(client, episode_with_user, test_db):
    """Test that query param token is used when both query param and header are present."""
    episode_id, token, headers = episode_with_user

    await test_db.execute(
        update(Episode).where(Episode.id == PyUUID(episode_id)).values(generation_status="complete")
    )
    await test_db.flush()

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress?token={token}",
        headers=headers
    )
    assert response.status_code == 200
