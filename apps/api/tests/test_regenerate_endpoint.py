"""
Integration tests for the ``/generation/episodes/{id}/regenerate`` endpoint.

Covers issue #213: ``regenerate_podcast`` previously called ``generate_podcast``
with positional arguments, which misaligned against the ``enable_composition`` /
``enable_distribution`` Query params and passed the unresolved ``Depends()``
sentinels as ``current_user`` / ``db`` — crashing with a 500 and (because the
status reset committed first) leaving the episode degraded. The endpoint now
delegates with explicit keyword arguments and does not pre-reset the episode.
"""

import pytest
from typing import Any
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from httpx import AsyncClient

from src.routers.generation import regenerate_podcast

Headers = dict[str, str]

# Long enough to satisfy the text source validator (>=50 chars, >=10 words).
SAMPLE_TEXT = (
    "This is a sufficiently long sample body of text that comfortably exceeds "
    "the minimum length and word-count requirements for a podcast content source."
)


@pytest.fixture
async def episode_with_content(client: AsyncClient) -> tuple[str, Headers]:
    """Create user + project + episode + text content source.

    Returns (episode_id, auth_headers). The text source lets ``generate_podcast``
    pass content validation so regeneration reaches the dispatch path.
    """
    reg = await client.post("/auth/register", json={
        "email": f"regen_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Regen Tester",
    })
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    proj = await client.post("/projects", headers=headers, json={
        "name": "Regen Project",
        "podcast_metadata": {
            "show_title": "Regen Show",
            "author": "Author",
            "description": "Desc",
        },
    })
    assert proj.status_code == 201, proj.text
    project_id = proj.json()["id"]

    ep = await client.post("/episodes", headers=headers, json={
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {"title": "Ep", "description": "Episode"},
    })
    assert ep.status_code == 201, ep.text
    episode_id = ep.json()["id"]

    content = await client.post(
        f"/episodes/{episode_id}/content?auto_extract=false",
        headers=headers,
        json={
            "episode_id": episode_id,
            "source_type": "text",
            "source_data": {"content": SAMPLE_TEXT},
        },
    )
    assert content.status_code == 201, content.text

    return episode_id, headers


@pytest.mark.asyncio
async def test_regenerate_happy_path(client, episode_with_content):
    """POST /regenerate queues generation and returns 202 with the episode id."""
    episode_id, headers = episode_with_content

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-regen-123")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/regenerate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    body: dict[str, Any] = resp.json()
    assert body["status"] == "queued"
    assert body["episode_id"] == episode_id
    mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_regenerate_requires_authentication(client, episode_with_content):
    """POST /regenerate without a token returns 401 (the prior bug returned 500)."""
    episode_id, _ = episode_with_content

    resp = await client.post(f"/generation/episodes/{episode_id}/regenerate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_regenerate_nonexistent_episode(client, episode_with_content):
    """POST /regenerate for an unknown episode returns 404."""
    _, headers = episode_with_content
    fake_episode_id = uuid4()

    resp = await client.post(
        f"/generation/episodes/{fake_episode_id}/regenerate", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_does_not_degrade_episode_on_failure():
    """A failed regenerate must not commit a degraded reset to the episode.

    The original bug reset ``generation_status`` to ``"draft"`` and wiped
    ``generation_progress`` and committed BEFORE delegating, so any subsequent
    failure left the episode degraded. The fix delegates directly to
    ``generate_podcast`` with no pre-reset, so when generation fails validation
    (no content source -> HTTP 400) nothing is mutated or committed first.

    Driven at the unit level: the shared test-DB transaction is rolled back on
    any erroring request, so persisted state cannot be re-read through the API.
    """
    episode = MagicMock()
    episode.generation_status = "complete"
    episode.generation_progress = {"stage": "complete", "progress": 100}

    # First db.execute -> episode lookup; second -> content sources (none).
    # The generate query eager-loads relationships, so it reads the episode via
    # ``.unique().scalar_one_or_none()`` (issue #217). A 'complete' status keeps the
    # episode restartable so it passes the in-progress guard (#214) and reaches the
    # no-content 400 this test asserts on.
    episode_result = MagicMock()
    episode_result.unique.return_value.scalar_one_or_none.return_value = episode
    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute.side_effect = [episode_result, content_result]

    current_user = MagicMock()
    current_user.tenant_id = uuid4()

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        with pytest.raises(HTTPException) as exc_info:
            await regenerate_podcast(
                episode_id=uuid4(), current_user=current_user, db=db
            )

    # No usable content -> 400, and crucially nothing was queued or committed,
    # and the episode's status/progress were never reset to a degraded state.
    assert exc_info.value.status_code == 400
    mock_delay.assert_not_called()
    db.commit.assert_not_called()
    assert episode.generation_status == "complete"
    assert episode.generation_progress == {"stage": "complete", "progress": 100}
