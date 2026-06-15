"""
Integration tests for the generation router's content-assembly + validation.

Covers issue #204: file/PDF sources must be pre-extracted into ``text`` (podcastfy
0.4.1 cannot read raw s3_keys), YouTube/URL/text sources flow through ``urls`` /
``text_content``, and the task must never be dispatched with ``file_paths``.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_http_200():
    """Return a context-manager mock that yields a 200 HEAD response (URL validator)."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.head = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
async def episode_and_auth(client):
    """Create user + project + episode, return (episode_id, auth_headers)."""
    reg = await client.post("/auth/register", json={
        "email": f"gen_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Gen Tester",
    })
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    proj = await client.post("/projects", headers=headers, json={
        "name": "Gen Project",
        "podcast_metadata": {
            "show_title": "Gen Show",
            "author": "Author",
            "description": "Desc",
        },
    })
    assert proj.status_code == 201
    project_id = proj.json()["id"]

    ep = await client.post("/episodes", headers=headers, json={
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {"title": "Ep", "description": "Episode"},
    })
    assert ep.status_code == 201
    return ep.json()["id"], headers


async def _create_pdf_source(client, episode_id, headers):
    resp = await client.post(
        f"/episodes/{episode_id}/content?auto_extract=false",
        headers=headers,
        json={
            "episode_id": episode_id,
            "source_type": "pdf",
            "source_data": {"filename": "doc.pdf", "s3_key": "uploads/doc.pdf"},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mark_complete(client, content_id, headers, extracted):
    resp = await client.put(
        f"/content/{content_id}",
        headers=headers,
        json={"extraction_status": "complete", "extracted_content": extracted},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_generate_rejects_unextracted_file_source(client, episode_and_auth):
    """A PDF source still pending extraction must yield HTTP 400, not dispatch."""
    episode_id, headers = episode_and_auth
    source = await _create_pdf_source(client, episode_id, headers)

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 400
    assert source["id"] in resp.json()["detail"]
    mock_delay.assert_not_called()


@pytest.mark.asyncio
async def test_generate_passes_extracted_pdf_as_text(client, episode_and_auth):
    """An extracted PDF source flows into text_content; no file_paths kwarg."""
    episode_id, headers = episode_and_auth
    source = await _create_pdf_source(client, episode_id, headers)
    await _mark_complete(client, source["id"], headers, "Extracted PDF body.")

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-123")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    mock_delay.assert_called_once()
    call_kwargs = mock_delay.call_args.kwargs
    assert "file_paths" not in call_kwargs
    assert call_kwargs["text_content"] == "Extracted PDF body."


@pytest.mark.asyncio
async def test_generate_passes_url_source_via_urls(client, episode_and_auth):
    """A URL source (no extraction) falls back to source_data and flows via urls."""
    episode_id, headers = episode_and_auth

    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=_mock_http_200(),
    ):
        resp = await client.post(
            f"/episodes/{episode_id}/content?auto_extract=false",
            headers=headers,
            json={
                "episode_id": episode_id,
                "source_type": "url",
                "source_data": {"url": "https://example.com/a", "title": "A"},
            },
        )
    assert resp.status_code == 201, resp.text

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-456")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    call_kwargs = mock_delay.call_args.kwargs
    assert "file_paths" not in call_kwargs
    assert "https://example.com/a" in call_kwargs["urls"]
