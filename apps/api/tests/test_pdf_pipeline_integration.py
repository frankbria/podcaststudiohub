"""
End-to-end integration test for the PDF pipeline (issue #210).

Exercises the full upload → extract → generate flow with S3 and the Podcastfy
engine mocked, proving that:
- A PDF upload stores the file (S3) and records s3_key/filename on a 'pdf' source.
- Extraction downloads the PDF from S3 by its s3_key and populates
  extracted_content, transitioning pending → extracting → complete.
- Generation then resolves the source to extracted text (never a raw s3_key),
  dispatching the engine with text_content rather than rejecting the file source.
"""

import io
import pytest
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch

from src.services.content_extraction_service import ContentExtractionService


def _pdf_files(filename: str = "whitepaper.pdf"):
    payload = b"%PDF-1.4\n" + b"0" * 2048
    return {"file": (filename, io.BytesIO(payload), "application/pdf")}


@pytest.fixture
async def episode_and_auth(client):
    """Create a user, project, and episode; return (episode_id, headers)."""
    reg = await client.post("/auth/register", json={
        "email": f"test_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Test User",
    })
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    proj = await client.post("/projects", headers=headers, json={
        "name": "PDF Project",
        "podcast_metadata": {
            "show_title": "Show", "author": "Author", "description": "Desc",
        },
    })
    assert proj.status_code == 201
    project_id = proj.json()["id"]

    ep = await client.post("/episodes", headers=headers, json={
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {"title": "Ep", "description": "Desc"},
    })
    assert ep.status_code == 201
    return ep.json()["id"], headers


@pytest.mark.asyncio
async def test_pdf_upload_extract_generate_pipeline(client, test_db, episode_and_auth):
    episode_id, headers = episode_and_auth

    # ---- 1. Upload the PDF (no auto-extract; we drive extraction explicitly) ----
    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ) as mock_upload:
        mock_upload.return_value = "https://bucket.s3.amazonaws.com/content/x.pdf"
        upload = await client.post(
            f"/episodes/{episode_id}/content/upload",
            headers=headers,
            files=_pdf_files(),
            data={"auto_extract": "false"},
        )

    assert upload.status_code == 201
    source = upload.json()
    content_id = source["id"]
    s3_key = source["source_data"]["s3_key"]
    assert source["extraction_status"] == "pending"
    assert s3_key  # recorded for extraction to resolve

    # ---- 2. Extract: downloads from S3 by s3_key, populates extracted_content ----
    extracted_text = "Extracted whitepaper body. " * 20
    service = ContentExtractionService()

    with patch(
        "src.services.content_extraction_service.settings.AWS_S3_BUCKET", "test-bucket"
    ), patch(
        "src.services.content_extraction_service.StorageService"
    ) as mock_storage_cls, patch.object(
        service.pdf_extractor, "extract_content", return_value=extracted_text
    ):
        mock_storage = mock_storage_cls.return_value
        mock_storage.download_file = AsyncMock(return_value="/tmp/x.pdf")

        result = await service.extract_from_pdf(test_db, UUID(content_id))

    assert result.success is True
    # The s3_key (not a local data/uploads path) is what was downloaded
    assert mock_storage.download_file.call_args[0][0] == s3_key

    # Status transitioned to complete and extracted_content is populated
    status_resp = await client.get(
        f"/content/{content_id}/extraction-status", headers=headers
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["extraction_status"] == "complete"

    # ---- 3. Generate: source resolves to text, engine gets text_content ----
    with patch("src.routers.generation.generate_podcast_task") as mock_task:
        mock_task.apply_async.return_value.id = "celery-task-123"
        gen = await client.post(
            f"/generation/episodes/{episode_id}/generate", headers=headers
        )

    assert gen.status_code == 202
    mock_task.apply_async.assert_called_once()
    kwargs = mock_task.apply_async.call_args.kwargs["kwargs"]
    # The PDF was resolved to extracted text — not rejected as an unextracted file
    assert kwargs["text_content"] is not None
    assert "Extracted whitepaper body" in kwargs["text_content"]
