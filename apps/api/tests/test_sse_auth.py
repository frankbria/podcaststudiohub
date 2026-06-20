"""
Tests for SSE (Server-Sent Events) authentication.

The SSE progress endpoint authenticates via the standard ``Authorization: Bearer``
header only. The browser ``EventSource`` API cannot send custom headers, so the web
client reaches this endpoint through a same-origin Next.js proxy that injects the
header server-side (issue #212). The legacy ``?token=<jwt>`` query-parameter auth
path has been removed because tokens in URLs leak into proxy/access logs, browser
history, and Referer headers.
"""
import json
import pytest
from types import SimpleNamespace
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
async def test_progress_stream_with_header_token(client, episode_with_user, test_db):
    """SSE endpoint authenticates via the Authorization header."""
    episode_id, token, headers = episode_with_user

    # Set episode to "complete" so the SSE stream terminates after one event.
    # Without this, the endpoint loops forever (while True / sleep 2s) and the
    # test hangs because httpx reads the full response body.
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
    # The per-poll fresh session must re-apply tenant context; otherwise FORCE
    # ROW LEVEL SECURITY (podcastfy_app role) hides the episode and the stream
    # emits nothing. Assert the streamed event carries the episode's status (#220).
    payload = json.loads(response.text.split("data: ", 1)[1].split("\n\n", 1)[0])
    assert payload["episode_id"] == episode_id
    assert payload["status"] == "complete"


@pytest.mark.asyncio
async def test_progress_stream_query_token_is_rejected(client, episode_with_user, test_db):
    """A JWT supplied only in the ?token= query string must NOT authenticate.

    This is the core of issue #212: tokens must never travel in the URL, so the
    query-parameter auth path is gone and a query-only token is treated as no
    credentials at all (401).
    """
    episode_id, token, _ = episode_with_user

    await test_db.execute(
        update(Episode).where(Episode.id == PyUUID(episode_id)).values(generation_status="complete")
    )
    await test_db.flush()

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress?token={token}"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_without_token(client, episode_with_user):
    """SSE endpoint returns 401 when no token is provided."""
    episode_id, _, _ = episode_with_user

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_with_invalid_token(client, episode_with_user):
    """SSE endpoint returns 401 for an invalid header token."""
    episode_id, _, _ = episode_with_user

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress",
        headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_with_expired_token(client, episode_with_user, test_db):
    """SSE endpoint returns 401 for an expired token."""
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
            f"/generation/episodes/{episode_id}/progress",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_progress_stream_tenant_isolation(client, episode_with_user):
    """A user cannot access another user's episode progress stream."""
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
        f"/generation/episodes/{episode_id}/progress",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert response.status_code == 404


# =============================================================================
# Tests: SSE per-iteration session (issue #220)
# =============================================================================

class _FakeSession:
    """Async-context-manager session whose .get() returns a preset episode.

    Stands in for a per-poll streaming session so the SSE generator can be
    exercised without touching the request-scoped session it must NOT reuse,
    and without opening real connections (issue #220).
    """

    opened = 0

    def __init__(self, episode):
        self._episode = episode

    async def __aenter__(self):
        type(self).opened += 1
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        # Absorb the SET LOCAL app.tenant_id call the generator issues.
        return None

    async def get(self, model, pk):
        return self._episode


@pytest.mark.asyncio
async def test_progress_stream_uses_fresh_session_per_poll(client, episode_with_user):
    """The SSE generator opens a fresh streaming session per poll (via the
    injectable factory) instead of reusing the request-scoped session,
    preventing pool leaks on disconnect (#220)."""
    from src.main import app
    from src.database import get_streaming_session_factory

    episode_id, token, headers = episode_with_user

    fake_episode = SimpleNamespace(
        id=PyUUID(episode_id),
        generation_status="complete",  # terminal → stream emits once and stops
        generation_progress={"stage": "complete", "progress": 100},
    )
    _FakeSession.opened = 0

    # Override the streaming factory for this test; the per-test override added
    # in conftest is replaced here and cleared by the client fixture teardown.
    app.dependency_overrides[get_streaming_session_factory] = (
        lambda: (lambda: _FakeSession(fake_episode))
    )

    response = await client.get(
        f"/generation/episodes/{episode_id}/progress",
        headers=headers,
    )

    assert response.status_code == 200
    # A fresh streaming session was opened by the generator (not the request one).
    assert _FakeSession.opened >= 1
    # The streamed event reflects the data fetched via that fresh session.
    payload = json.loads(response.text.split("data: ", 1)[1].split("\n\n", 1)[0])
    assert payload["status"] == "complete"


@pytest.mark.asyncio
async def test_progress_stream_nonexistent_episode(client, registered_user):
    """SSE endpoint returns 404 for a non-existent episode."""
    token, headers = registered_user
    fake_episode_id = uuid4()

    response = await client.get(
        f"/generation/episodes/{fake_episode_id}/progress",
        headers=headers
    )
    assert response.status_code == 404
