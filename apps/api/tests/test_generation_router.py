"""
Integration tests for the generation router's content-assembly + validation.

Covers issue #204: file/PDF sources must be pre-extracted into ``text`` (podcastfy
0.4.1 cannot read raw s3_keys), YouTube/URL/text sources flow through ``urls`` /
``text_content``, and the task must never be dispatched with ``file_paths``.
"""

import pytest
from typing import Any
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from httpx import AsyncClient

Headers = dict[str, str]


def _mock_http_200() -> AsyncMock:
    """Return a context-manager mock that yields a 200 HEAD response (URL validator)."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.head = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
async def episode_and_auth(client: AsyncClient) -> tuple[str, Headers]:
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


async def _create_pdf_source(client: AsyncClient, episode_id: str, headers: Headers) -> dict[str, Any]:
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


async def _mark_complete(client: AsyncClient, content_id: str, headers: Headers, extracted: str) -> None:
    resp = await client.put(
        f"/content/{content_id}",
        headers=headers,
        json={"extraction_status": "complete", "extracted_content": extracted},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Issue #217: episode/project TTS provider + conversation_config must be
# forwarded to the Celery task (otherwise every podcast silently uses OpenAI).
# ---------------------------------------------------------------------------

# Text long enough to clear the source validator (>=50 chars, >=10 words).
_TEXT_BODY = (
    "This is a sufficiently long piece of text content used by the generation "
    "tests so that source validation accepts it as a usable podcast source."
)

ELEVENLABS_TTS_CONFIG = {
    "model": "eleven_multilingual_v2",
    "voice_1_id": "21m00Tcm4TlvDq8ikWAM",
    "voice_2_id": "AZnzlk1XvdvUeBnXmlld",
}
GEMINI_TTS_CONFIG = {"model": "en-US-Studio-MultiSpeaker", "language_code": "en-US"}


async def _create_text_source(client: AsyncClient, episode_id: str, headers: Headers) -> None:
    """Attach a usable text content source so generation has something to do."""
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


async def _create_tts_config(
    client: AsyncClient, headers: Headers, provider: str, config: dict[str, Any]
) -> str:
    """Create a TTS configuration via the API and return its id."""
    resp = await client.post(
        "/tts-configs",
        headers=headers,
        json={"name": f"{provider} cfg", "provider": provider, "config": config},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_template(client: AsyncClient, headers: Headers, config: dict[str, Any]) -> str:
    """Create a conversation template via the API and return its id."""
    resp = await client.post(
        "/conversation-templates",
        headers=headers,
        json={"name": "Tmpl", "description": "t", "config": config},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
async def episode_project_and_auth(client: AsyncClient) -> tuple[str, str, Headers]:
    """Create user + project + episode, return (episode_id, project_id, auth_headers)."""
    reg = await client.post("/auth/register", json={
        "email": f"gencfg_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Gen Cfg Tester",
    })
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    proj = await client.post("/projects", headers=headers, json={
        "name": "Gen Cfg Project",
        "podcast_metadata": {"show_title": "Show", "author": "A", "description": "D"},
    })
    assert proj.status_code == 201
    project_id = proj.json()["id"]

    ep = await client.post("/episodes", headers=headers, json={
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {"title": "Ep", "description": "Episode"},
    })
    assert ep.status_code == 201
    return ep.json()["id"], project_id, headers


@pytest.mark.asyncio
async def test_generate_forwards_episode_tts_provider(client, episode_project_and_auth):
    """A non-OpenAI episode TTS config is forwarded as tts_model to the task."""
    episode_id, _project_id, headers = episode_project_and_auth
    await _create_text_source(client, episode_id, headers)

    tts_id = await _create_tts_config(client, headers, "elevenlabs", ELEVENLABS_TTS_CONFIG)
    upd = await client.put(
        f"/episodes/{episode_id}", headers=headers, json={"tts_config_id": tts_id}
    )
    assert upd.status_code == 200, upd.text

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-tts")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    mock_delay.assert_called_once()
    assert mock_delay.call_args.kwargs["tts_model"] == "elevenlabs"


@pytest.mark.asyncio
async def test_generate_falls_back_to_project_default_tts(client, episode_project_and_auth):
    """With no episode TTS config, the project default provider is forwarded."""
    episode_id, project_id, headers = episode_project_and_auth
    await _create_text_source(client, episode_id, headers)

    tts_id = await _create_tts_config(client, headers, "gemini", GEMINI_TTS_CONFIG)
    upd = await client.put(
        f"/projects/{project_id}", headers=headers, json={"default_tts_config_id": tts_id}
    )
    assert upd.status_code == 200, upd.text

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-gemini")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    mock_delay.assert_called_once()
    assert mock_delay.call_args.kwargs["tts_model"] == "gemini"


@pytest.mark.asyncio
async def test_generate_normalizes_gemini_multi_provider(client, episode_project_and_auth):
    """The app's 'gemini_multi' provider is normalized to podcastfy's 'geminimulti'."""
    episode_id, _project_id, headers = episode_project_and_auth
    await _create_text_source(client, episode_id, headers)

    tts_id = await _create_tts_config(client, headers, "gemini_multi", GEMINI_TTS_CONFIG)
    upd = await client.put(
        f"/episodes/{episode_id}", headers=headers, json={"tts_config_id": tts_id}
    )
    assert upd.status_code == 200, upd.text

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-gm")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    kwargs = mock_delay.call_args.kwargs
    assert kwargs["tts_model"] == "geminimulti"
    # The nested text_to_speech block is keyed by the normalized provider name.
    assert "geminimulti" in kwargs["conversation_config"]["text_to_speech"]
    assert kwargs["conversation_config"]["text_to_speech"]["default_tts_model"] == "geminimulti"


@pytest.mark.asyncio
async def test_generate_forwards_conversation_config(client, episode_project_and_auth):
    """An episode template + TTS config produce a conversation_config dict."""
    episode_id, _project_id, headers = episode_project_and_auth
    await _create_text_source(client, episode_id, headers)

    template_cfg = {
        "word_count": 300,
        "conversation_style": ["casual"],
        "roles_person1": "host",
        "roles_person2": "expert guest",
        "dialogue_structure": ["Introduction", "Main Content", "Conclusion"],
        "podcast_name": "X",
        "output_language": "en",
        "creativity": 0.7,
    }
    template_id = await _create_template(client, headers, template_cfg)
    tts_id = await _create_tts_config(client, headers, "elevenlabs", ELEVENLABS_TTS_CONFIG)
    upd = await client.put(
        f"/episodes/{episode_id}",
        headers=headers,
        json={"template_id": template_id, "tts_config_id": tts_id},
    )
    assert upd.status_code == 200, upd.text

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-cfg")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    conv = mock_delay.call_args.kwargs["conversation_config"]
    # Template fields are forwarded at the top level (podcastfy reads them there).
    assert conv["word_count"] == 300
    # The flat TTS config is translated into podcastfy's nested text_to_speech
    # schema so the user's model + voices are actually honored (issue #217).
    tts = conv["text_to_speech"]
    assert tts["default_tts_model"] == "elevenlabs"
    assert tts["elevenlabs"]["model"] == "eleven_multilingual_v2"
    assert tts["elevenlabs"]["default_voices"] == {
        "question": "21m00Tcm4TlvDq8ikWAM",
        "answer": "AZnzlk1XvdvUeBnXmlld",
    }


@pytest.mark.asyncio
async def test_generate_without_config_uses_task_default(client, episode_project_and_auth):
    """With no TTS/template config, the task default (openai) is preserved."""
    episode_id, _project_id, headers = episode_project_and_auth
    await _create_text_source(client, episode_id, headers)

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-default")
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 202, resp.text
    call_kwargs = mock_delay.call_args.kwargs
    # Not passed → task default tts_model="openai" / conversation_config=None applies.
    assert "tts_model" not in call_kwargs
    assert "conversation_config" not in call_kwargs


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


# ---------------------------------------------------------------------------
# Issue #214: re-submitting generation for an in-progress episode must be
# rejected with HTTP 409 (otherwise two tasks race to write s3_url/s3_key/
# generation_status and the in-progress celery_task_id is overwritten).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_rejects_when_already_in_progress(client, episode_and_auth):
    """A second generate while status is in-progress (queued) yields 409, no re-dispatch."""
    episode_id, headers = episode_and_auth
    await _create_text_source(client, episode_id, headers)

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-1")
        first = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )
        assert first.status_code == 202, first.text
        assert first.json()["status"] == "queued"

        # Episode is now 'queued' (in-progress); a second submission must be rejected.
        second = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert second.status_code == 409, second.text
    # Current status is surfaced in the detail for debugging clarity.
    assert "queued" in second.json()["detail"].lower()
    # Only the first submission dispatched a task.
    mock_delay.assert_called_once()


@pytest.mark.parametrize("restartable_status", ["draft", "complete", "failed"])
@pytest.mark.asyncio
async def test_generate_allowed_from_restartable_status(restartable_status):
    """draft/complete/failed are restartable: the guard lets generation re-dispatch.

    Unit-level (mirrors ``test_regenerate_does_not_degrade_episode_on_failure``):
    the shared test-DB transaction can't be re-read through the API after a status
    mutation, so the guard's allow-set is exercised against a mocked episode.
    """
    from src.routers.generation import generate_podcast

    episode = MagicMock()
    episode.generation_status = restartable_status
    # No TTS/template/project config -> tts_model / conversation_config stay unset.
    episode.tts_config = None
    episode.template = None
    episode.project = None

    source = MagicMock()
    source.source_type = "text"
    source.extraction_status = "complete"
    source.extracted_content = _TEXT_BODY

    episode_result = MagicMock()
    episode_result.unique.return_value.scalar_one_or_none.return_value = episode
    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = [source]

    db = AsyncMock()
    db.execute.side_effect = [episode_result, content_result]

    current_user = MagicMock()
    current_user.tenant_id = uuid4()

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-restart")
        result = await generate_podcast(
            episode_id=uuid4(),
            enable_composition=False,
            enable_distribution=False,
            current_user=current_user,
            db=db,
        )

    # Guard allowed it through: a task was dispatched and status reset to queued.
    mock_delay.assert_called_once()
    assert result["status"] == "queued"
    assert episode.generation_status == "queued"


@pytest.mark.parametrize(
    "in_progress_status",
    ["queued", "extracting", "generating", "uploading", "composing", "distributing"],
)
@pytest.mark.asyncio
async def test_generate_rejects_each_in_progress_status(in_progress_status):
    """Every non-restartable status is rejected with 409 before any dispatch."""
    from src.routers.generation import generate_podcast

    episode = MagicMock()
    episode.generation_status = in_progress_status

    episode_result = MagicMock()
    episode_result.unique.return_value.scalar_one_or_none.return_value = episode

    db = AsyncMock()
    db.execute.side_effect = [episode_result]

    current_user = MagicMock()
    current_user.tenant_id = uuid4()

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        with pytest.raises(HTTPException) as exc_info:
            await generate_podcast(
                episode_id=uuid4(),
                enable_composition=False,
                enable_distribution=False,
                current_user=current_user,
                db=db,
            )

    assert exc_info.value.status_code == 409
    assert in_progress_status in exc_info.value.detail
    mock_delay.assert_not_called()


@pytest.mark.asyncio
async def test_generate_rejects_when_no_usable_content(client, episode_and_auth):
    """If every source is skipped (e.g. source_data mutated to drop its url), reject."""
    episode_id, headers = episode_and_auth

    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=_mock_http_200(),
    ):
        create = await client.post(
            f"/episodes/{episode_id}/content?auto_extract=false",
            headers=headers,
            json={
                "episode_id": episode_id,
                "source_type": "url",
                "source_data": {"url": "https://example.com/a", "title": "A"},
            },
        )
    assert create.status_code == 201, create.text
    source_id = create.json()["id"]

    # The update path does not re-validate source_data, so the url can become
    # whitespace-only — which must be treated as no usable content.
    upd = await client.put(
        f"/content/{source_id}",
        headers=headers,
        json={"source_data": {"url": "   ", "title": "A"}},
    )
    assert upd.status_code == 200, upd.text

    with patch("src.routers.generation.generate_podcast_task.delay") as mock_delay:
        resp = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert resp.status_code == 400
    assert "nothing to generate" in resp.json()["detail"].lower()
    mock_delay.assert_not_called()
