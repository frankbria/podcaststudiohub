"""
Integration + service tests for issue #211: platform distribution must actually
be triggered from generation with non-empty metadata.

Covers:
- ``get_active_distribution_targets_for_project`` returns only active targets for
  the requested project.
- The generation router loads those targets and forwards a ``platforms`` mapping
  to the Celery task (the task gates distribution on ``bool(platforms)``).
"""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch

from httpx import AsyncClient

from src.routers import generation as generation_router
from src.database import set_tenant_context
from src.services.distribution_target_service import (
    get_active_distribution_targets_for_project,
)

Headers = dict[str, str]

# Text long enough to clear the source validator (>=50 chars, >=10 words).
_TEXT_BODY = (
    "This is a sufficiently long piece of text content used by the distribution "
    "wiring tests so that source validation accepts it as a usable podcast source."
)


async def _register(client: AsyncClient) -> Headers:
    reg = await client.post("/auth/register", json={
        "email": f"dist_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Dist Tester",
    })
    assert reg.status_code == 201, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _create_project(client: AsyncClient, headers: Headers, name: str = "Dist Project") -> str:
    proj = await client.post("/projects", headers=headers, json={
        "name": name,
        "podcast_metadata": {"show_title": "Show", "author": "A", "description": "D"},
    })
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


async def _create_episode(client: AsyncClient, headers: Headers, project_id: str) -> str:
    ep = await client.post("/episodes", headers=headers, json={
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {"title": "Ep", "description": "Episode"},
    })
    assert ep.status_code == 201, ep.text
    return ep.json()["id"]


async def _create_text_source(client: AsyncClient, episode_id: str, headers: Headers) -> None:
    resp = await client.post(
        f"/episodes/{episode_id}/content?auto_extract=false",
        headers=headers,
        json={
            "episode_id": episode_id,
            "source_type": "text",
            "source_data": {"content": _TEXT_BODY},
        },
    )
    assert resp.status_code == 201, resp.text


async def _create_webhook_target(
    client: AsyncClient, headers: Headers, project_id: str | None, url: str
) -> dict:
    body = {
        "name": "Hook",
        "url": url,
        "method": "POST",
        "headers": {"Authorization": "Bearer secret-token"},
    }
    if project_id is not None:
        body["project_id"] = project_id
    resp = await client.post("/distribution-targets/webhook", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Service: get_active_distribution_targets_for_project
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_targets_returns_only_active_for_project(client, test_db):
    """Returns active targets for the project; excludes inactive ones."""
    headers = await _register(client)
    project_id = await _create_project(client, headers)

    active = await _create_webhook_target(
        client, headers, project_id, "https://hook.example.com/active"
    )
    inactive = await _create_webhook_target(
        client, headers, project_id, "https://hook.example.com/inactive"
    )
    # Deactivate the second target.
    upd = await client.put(
        f"/distribution-targets/{inactive['id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert upd.status_code == 200, upd.text

    await set_tenant_context(test_db, active["tenant_id"])
    targets = await get_active_distribution_targets_for_project(test_db, project_id)

    returned_ids = {str(t.id) for t in targets}
    assert active["id"] in returned_ids
    assert inactive["id"] not in returned_ids
    assert all(t.is_active for t in targets)


@pytest.mark.asyncio
async def test_active_targets_excludes_other_projects(client, test_db):
    """Targets scoped to a different project are not returned."""
    headers = await _register(client)
    project_a = await _create_project(client, headers, "A")
    project_b = await _create_project(client, headers, "B")

    target_a = await _create_webhook_target(
        client, headers, project_a, "https://hook.example.com/a"
    )
    await _create_webhook_target(client, headers, project_b, "https://hook.example.com/b")

    await set_tenant_context(test_db, target_a["tenant_id"])
    targets = await get_active_distribution_targets_for_project(test_db, project_a)

    assert {str(t.id) for t in targets} == {target_a["id"]}


@pytest.mark.asyncio
async def test_active_targets_empty_when_none(client, test_db):
    """A project with no targets yields an empty list."""
    headers = await _register(client)
    project_id = await _create_project(client, headers)
    # Seed an unrelated target so a tenant context exists and the table is non-empty.
    other = await _create_webhook_target(
        client, headers, await _create_project(client, headers, "Other"),
        "https://hook.example.com/other",
    )

    await set_tenant_context(test_db, other["tenant_id"])
    targets = await get_active_distribution_targets_for_project(test_db, project_id)

    assert targets == []


# ---------------------------------------------------------------------------
# Router: platforms mapping forwarded to the Celery task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_forwards_platforms_when_distribution_enabled(client):
    """An active target + enable_distribution=true forwards a platforms mapping."""
    headers = await _register(client)
    project_id = await _create_project(client, headers)
    episode_id = await _create_episode(client, headers, project_id)
    await _create_text_source(client, episode_id, headers)
    await _create_webhook_target(
        client, headers, project_id, "https://hook.example.com/publish"
    )

    with patch.object(generation_router.settings, "ENABLE_PLATFORM_DISTRIBUTION", True), \
         patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-dist")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate?enable_distribution=true",
            headers=headers,
        )

    assert resp.status_code == 202, resp.text
    mock_delay.assert_called_once()
    kwargs = mock_delay.call_args.kwargs
    assert kwargs["enable_distribution"] is True
    platforms = kwargs["platforms"]
    assert "webhook" in platforms
    assert platforms["webhook"]["url"] == "https://hook.example.com/publish"


@pytest.mark.asyncio
async def test_generate_omits_platforms_when_no_targets(client):
    """Distribution enabled but no targets configured → no platforms kwarg."""
    headers = await _register(client)
    project_id = await _create_project(client, headers)
    episode_id = await _create_episode(client, headers, project_id)
    await _create_text_source(client, episode_id, headers)

    with patch.object(generation_router.settings, "ENABLE_PLATFORM_DISTRIBUTION", True), \
         patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-nodist")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate?enable_distribution=true",
            headers=headers,
        )

    assert resp.status_code == 202, resp.text
    mock_delay.assert_called_once()
    assert "platforms" not in mock_delay.call_args.kwargs


@pytest.mark.asyncio
async def test_generate_omits_platforms_when_distribution_disabled(client):
    """An active target is ignored when distribution is not requested."""
    headers = await _register(client)
    project_id = await _create_project(client, headers)
    episode_id = await _create_episode(client, headers, project_id)
    await _create_text_source(client, episode_id, headers)
    await _create_webhook_target(
        client, headers, project_id, "https://hook.example.com/ignored"
    )

    with patch.object(generation_router.settings, "ENABLE_PLATFORM_DISTRIBUTION", True), \
         patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-off")
        # enable_distribution defaults to false here.
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate",
            headers=headers,
        )

    assert resp.status_code == 202, resp.text
    mock_delay.assert_called_once()
    assert "platforms" not in mock_delay.call_args.kwargs
    assert mock_delay.call_args.kwargs["enable_distribution"] is False
