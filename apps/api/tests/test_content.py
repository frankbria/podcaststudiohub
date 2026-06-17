"""
Comprehensive test suite for content source API endpoints.

Includes integration tests for source data validation (GAP-015).

Tests cover:
- CRUD operations for all three source types (URL, PDF, text)
- Episode relationship validation (invalid episode_id)
- Source type validation (missing required fields per type)
- Extraction status tracking (initialization, transitions)
- Pagination with episode filtering
- Authentication requirements
- Tenant isolation (skipped with justification)
"""

import io
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch



# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def authenticated_headers(client):
    """Create authenticated user and return auth headers."""
    # Register user
    reg_response = await client.post("/auth/register", json={
        "email": f"test_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Test User"
    })
    assert reg_response.status_code == 201
    token = reg_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def project_and_auth(client):
    """Create user and project, return (project_id, auth_headers)."""
    # Register user
    reg_response = await client.post("/auth/register", json={
        "email": f"test_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Test User"
    })
    assert reg_response.status_code == 201
    token = reg_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    proj_response = await client.post("/projects", headers=headers, json={
        "name": "Test Project",
        "podcast_metadata": {
            "show_title": "Test Show",
            "author": "Test Author",
            "description": "Test Description"
        }
    })
    assert proj_response.status_code == 201
    project_id = proj_response.json()["id"]

    return project_id, headers


@pytest.fixture
async def episode_and_auth(client, project_and_auth):
    """Create episode for content source testing."""
    project_id, headers = project_and_auth

    # Create episode
    episode_data = {
        "project_id": project_id,
        "episode_number": 1,
        "episode_metadata": {
            "title": "Test Episode",
            "description": "Episode for content source testing"
        }
    }

    response = await client.post(
        "/episodes",
        headers=headers,
        json=episode_data
    )

    assert response.status_code == 201
    episode_id = response.json()["id"]

    return episode_id, headers


@pytest.fixture
async def url_content_source(client, episode_and_auth):
    """Create URL-type content source for testing."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "https://example.com/article",
            "title": "Test Article"
        }
    }

    mock_client = _mock_http_200()
    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        response = await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json=content_data
        )

    assert response.status_code == 201
    return response.json(), headers


@pytest.fixture
async def pdf_content_source(client, episode_and_auth):
    """Create PDF-type content source for testing."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "pdf",
        "source_data": {
            "filename": "document.pdf",
            "s3_key": "uploads/document.pdf"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 201
    return response.json(), headers


@pytest.fixture
async def text_content_source(client, episode_and_auth):
    """Create text-type content source for testing."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            "content": "This is a valid text sample for the podcast episode content source testing"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 201
    return response.json(), headers


# ============================================================================
# CRUD TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_url_content_source(client, episode_and_auth):
    """Test creating URL-type content source."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "https://example.com/article",
            "title": "Tech Article"
        }
    }

    mock_client = _mock_http_200()
    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        response = await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json=content_data
        )

    assert response.status_code == 201
    data = response.json()
    assert data["source_type"] == "url"
    assert data["source_data"]["url"] == "https://example.com/article"
    assert data["source_data"]["title"] == "Tech Article"
    assert data["extraction_status"] == "pending"
    assert data["extracted_content"] is None
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_pdf_content_source(client, episode_and_auth):
    """Test creating PDF-type content source."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "pdf",
        "source_data": {
            "filename": "research.pdf",
            "s3_key": "uploads/research.pdf"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 201
    data = response.json()
    assert data["source_type"] == "pdf"
    assert data["source_data"]["filename"] == "research.pdf"
    assert data["source_data"]["s3_key"] == "uploads/research.pdf"
    assert data["extraction_status"] == "pending"


@pytest.mark.asyncio
async def test_create_text_content_source(client, episode_and_auth):
    """Test creating text-type content source."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            "content": "This is the raw text content for the podcast episode"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 201
    data = response.json()
    assert data["source_type"] == "text"
    assert data["source_data"]["content"] == "This is the raw text content for the podcast episode"
    assert data["extraction_status"] == "pending"


@pytest.mark.asyncio
async def test_list_content_sources(client, episode_and_auth):
    """Test listing content sources for an episode."""
    episode_id, headers = episode_and_auth

    # Create multiple content sources
    sources = [
        {"episode_id": episode_id, "source_type": "url", "source_data": {"url": "https://example1.com", "title": "Article 1"}},
        {"episode_id": episode_id, "source_type": "pdf", "source_data": {"filename": "doc1.pdf", "s3_key": "uploads/doc1.pdf"}},
        {"episode_id": episode_id, "source_type": "text", "source_data": {"content": "This is valid text content for the podcast episode source item one"}},
    ]

    mock_client = _mock_http_200()
    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        for source in sources:
            await client.post(f"/episodes/{episode_id}/content", headers=headers, json=source)

    # List content sources
    response = await client.get(f"/episodes/{episode_id}/content", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["content_sources"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_get_content_source_by_id(client, url_content_source):
    """Test retrieving content source by ID."""
    content, headers = url_content_source

    response = await client.get(f"/content/{content['id']}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == content["id"]
    assert data["source_type"] == "url"


@pytest.mark.asyncio
async def test_get_nonexistent_content_source(client, authenticated_headers):
    """Test retrieving non-existent content source returns 404."""
    random_id = str(uuid4())

    response = await client.get(f"/content/{random_id}", headers=authenticated_headers)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_content_source(client, url_content_source):
    """Test updating content source."""
    content, headers = url_content_source

    update_data = {
        "extraction_status": "complete",
        "extracted_content": "This is the extracted content from the URL"
    }

    response = await client.put(
        f"/content/{content['id']}",
        headers=headers,
        json=update_data
    )

    assert response.status_code == 200
    data = response.json()
    assert data["extraction_status"] == "complete"
    assert data["extracted_content"] == "This is the extracted content from the URL"


@pytest.mark.asyncio
async def test_update_content_source_partial(client, pdf_content_source):
    """Test partial update of content source."""
    content, headers = pdf_content_source

    # Only update extraction_status
    update_data = {
        "extraction_status": "extracting"
    }

    response = await client.put(
        f"/content/{content['id']}",
        headers=headers,
        json=update_data
    )

    assert response.status_code == 200
    data = response.json()
    assert data["extraction_status"] == "extracting"
    # Original source_data should remain unchanged
    assert data["source_data"]["filename"] == "document.pdf"


@pytest.mark.asyncio
async def test_update_nonexistent_content_source(client, authenticated_headers):
    """Test updating non-existent content source returns 404."""
    random_id = str(uuid4())
    update_data = {"extraction_status": "complete"}

    response = await client.put(
        f"/content/{random_id}",
        headers=authenticated_headers,
        json=update_data
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_content_source(client, text_content_source):
    """Test deleting content source."""
    content, headers = text_content_source

    # Delete content source
    response = await client.delete(f"/content/{content['id']}", headers=headers)

    assert response.status_code == 204

    # Verify it's deleted
    get_response = await client.get(f"/content/{content['id']}", headers=headers)
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_content_source(client, authenticated_headers):
    """Test deleting non-existent content source returns 404."""
    random_id = str(uuid4())

    response = await client.delete(f"/content/{random_id}", headers=authenticated_headers)

    assert response.status_code == 404


# ============================================================================
# EPISODE RELATIONSHIP TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_content_source_invalid_episode(client, authenticated_headers):
    """Test creating content source with non-existent episode returns 404."""
    random_episode_id = str(uuid4())

    content_data = {
        "episode_id": random_episode_id,
        "source_type": "url",
        "source_data": {
            "url": "https://example.com",
            "title": "Test"
        }
    }

    response = await client.post(
        f"/episodes/{random_episode_id}/content",
        headers=authenticated_headers,
        json=content_data
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_content_source_mismatched_episode_id(client, episode_and_auth):
    """Test creating content source with mismatched episode IDs in path and body."""
    episode_id, headers = episode_and_auth
    different_id = str(uuid4())

    content_data = {
        "episode_id": different_id,  # Different from path
        "source_type": "url",
        "source_data": {
            "url": "https://example.com",
            "title": "Test"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 400
    assert "must match" in response.json()["detail"].lower()


# ============================================================================
# SOURCE TYPE VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_url_source_missing_url_field(client, episode_and_auth):
    """Test URL source without required 'url' field fails validation."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "title": "Test Article"
            # Missing 'url' field
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    assert "url" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_url_source_missing_title_field(client, episode_and_auth):
    """Test URL source without required 'title' field fails validation."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "https://example.com"
            # Missing 'title' field
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    assert "title" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_pdf_source_missing_filename_field(client, episode_and_auth):
    """Test PDF source without required 'filename' field fails validation."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "pdf",
        "source_data": {
            "s3_key": "uploads/doc.pdf"
            # Missing 'filename' field
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    assert "filename" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_pdf_source_missing_s3_key_field(client, episode_and_auth):
    """Test PDF source without required 's3_key' field fails validation."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "pdf",
        "source_data": {
            "filename": "document.pdf"
            # Missing 's3_key' field
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    assert "s3_key" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_text_source_missing_content_field(client, episode_and_auth):
    """Test text source without required 'content' field fails validation."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            # Missing 'content' field
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    assert "content" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_url_source_empty_url_field(client, episode_and_auth):
    """Test URL source with empty 'url' field fails validation."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "   ",  # Empty/whitespace
            "title": "Test"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422


# ============================================================================
# EXTRACTION STATUS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_content_source_initial_status_pending(client, episode_and_auth):
    """Test that newly created content sources have 'pending' extraction status."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "https://example.com",
            "title": "Test"
        }
    }

    mock_client = _mock_http_200()
    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        response = await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json=content_data
        )

    assert response.status_code == 201
    data = response.json()
    assert data["extraction_status"] == "pending"
    assert data["extracted_content"] is None
    assert data["error_message"] is None


@pytest.mark.asyncio
async def test_update_extraction_status_transitions(client, url_content_source):
    """Test extraction status can transition through workflow states."""
    content, headers = url_content_source

    # Transition: pending -> extracting
    response = await client.put(
        f"/content/{content['id']}",
        headers=headers,
        json={"extraction_status": "extracting"}
    )
    assert response.status_code == 200
    assert response.json()["extraction_status"] == "extracting"

    # Transition: extracting -> complete
    response = await client.put(
        f"/content/{content['id']}",
        headers=headers,
        json={
            "extraction_status": "complete",
            "extracted_content": "Extracted text from the article"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["extraction_status"] == "complete"
    assert data["extracted_content"] == "Extracted text from the article"


# ============================================================================
# PAGINATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_content_sources_pagination(client, episode_and_auth):
    """Test pagination with custom page size."""
    episode_id, headers = episode_and_auth

    # Create 5 content sources
    mock_client = _mock_http_200()
    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        for i in range(5):
            await client.post(
                f"/episodes/{episode_id}/content",
                headers=headers,
                json={
                    "episode_id": episode_id,
                    "source_type": "url",
                    "source_data": {
                        "url": f"https://example{i}.com",
                        "title": f"Article {i}"
                    }
                }
            )

    # Get page 1 with page_size=2
    response = await client.get(
        f"/episodes/{episode_id}/content?page=1&page_size=2",
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["content_sources"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 3


@pytest.mark.asyncio
async def test_list_content_sources_second_page(client, episode_and_auth):
    """Test retrieving second page of results."""
    episode_id, headers = episode_and_auth

    # Create 3 content sources
    for i in range(3):
        await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json={
                "episode_id": episode_id,
                "source_type": "text",
                "source_data": {"content": f"This is valid text content for the podcast episode source item number {i}"}
            }
        )

    # Get page 2 with page_size=2
    response = await client.get(
        f"/episodes/{episode_id}/content?page=2&page_size=2",
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["content_sources"]) == 1  # Only 1 item on page 2
    assert data["page"] == 2


@pytest.mark.asyncio
async def test_list_content_sources_empty_results(client, episode_and_auth):
    """Test listing content sources when episode has none."""
    episode_id, headers = episode_and_auth

    response = await client.get(
        f"/episodes/{episode_id}/content",
        headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["content_sources"]) == 0
    assert data["total_pages"] == 0


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_content_source_requires_auth(client, episode_and_auth):
    """Test creating content source without authentication fails."""
    episode_id, _ = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {"url": "https://example.com", "title": "Test"}
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        json=content_data
        # No headers - unauthenticated
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_content_sources_requires_auth(client, episode_and_auth):
    """Test listing content sources without authentication fails."""
    episode_id, _ = episode_and_auth

    response = await client.get(f"/episodes/{episode_id}/content")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_content_source_requires_auth(client, url_content_source):
    """Test getting content source without authentication fails."""
    content, _ = url_content_source

    response = await client.get(f"/content/{content['id']}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_content_source_requires_auth(client, url_content_source):
    """Test updating content source without authentication fails."""
    content, _ = url_content_source

    response = await client.put(
        f"/content/{content['id']}",
        json={"extraction_status": "complete"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_content_source_requires_auth(client, url_content_source):
    """Test deleting content source without authentication fails."""
    content, _ = url_content_source

    response = await client.delete(f"/content/{content['id']}")

    assert response.status_code == 401


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================

@pytest.mark.skip(reason="Test fixture transaction handling interferes with RLS. Manual/integration tests verify RLS works.")
@pytest.mark.asyncio
async def test_content_source_tenant_isolation(client, url_content_source):
    """
    Test that content sources are isolated by tenant via RLS.

    SKIPPED: Test fixture transaction handling interferes with RLS.
    RLS isolation is verified through manual/integration testing and
    the database-level RLS policies ensure tenant isolation.
    """
    pass


# ============================================================================
# SOURCE DATA VALIDATION TESTS (GAP-015)
# ============================================================================

def _mock_http_200():
    """Return a context-manager mock that yields a 200 HEAD response."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.head = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_create_url_content_source_invalid_scheme(client, episode_and_auth):
    """URL with non-http/https scheme should return 422."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "ftp://example.com/file",
            "title": "FTP Article"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "http" in detail.lower() or "scheme" in detail.lower()


@pytest.mark.asyncio
async def test_create_url_content_source_no_scheme(client, episode_and_auth):
    """URL without scheme should return 422."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "example.com/article",
            "title": "Article"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_url_content_source_unreachable(client, episode_and_auth):
    """URL that returns 404 should return 422 with descriptive error."""
    episode_id, headers = episode_and_auth

    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.head = AsyncMock(return_value=mock_response)

    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        content_data = {
            "episode_id": episode_id,
            "source_type": "url",
            "source_data": {
                "url": "https://example.com/missing",
                "title": "Missing Page"
            }
        }

        response = await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json=content_data
        )

    assert response.status_code == 422
    assert "404" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_url_content_source_timeout(client, episode_and_auth):
    """URL that times out should return 422 with timeout message."""
    import httpx as _httpx
    episode_id, headers = episode_and_auth

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.head = AsyncMock(side_effect=_httpx.TimeoutException("timeout"))

    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        content_data = {
            "episode_id": episode_id,
            "source_type": "url",
            "source_data": {
                "url": "https://slow.example.com",
                "title": "Slow Site"
            }
        }

        response = await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json=content_data
        )

    assert response.status_code == 422
    assert "timed out" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_url_content_source_valid_passes(client, episode_and_auth):
    """Valid URL returning 200 should create content source successfully."""
    episode_id, headers = episode_and_auth

    mock_client = _mock_http_200()

    with patch(
        "src.services.source_validator_service.httpx.AsyncClient",
        return_value=mock_client,
    ):
        content_data = {
            "episode_id": episode_id,
            "source_type": "url",
            "source_data": {
                "url": "https://example.com/article",
                "title": "Valid Article"
            }
        }

        response = await client.post(
            f"/episodes/{episode_id}/content",
            headers=headers,
            json=content_data
        )

    assert response.status_code == 201
    assert response.json()["source_type"] == "url"


@pytest.mark.asyncio
async def test_create_text_content_source_too_short(client, episode_and_auth):
    """Text content shorter than 50 chars should return 422."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            "content": "Too short"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "50" in detail or "short" in detail.lower()


@pytest.mark.asyncio
async def test_create_text_content_source_too_long(client, episode_and_auth):
    """Text content exceeding 50000 chars should return 422."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            "content": "word " * 15_000  # ~75000 chars
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "50000" in detail or "long" in detail.lower()


@pytest.mark.asyncio
async def test_create_text_content_source_valid_passes(client, episode_and_auth):
    """Valid text content (50+ chars, 10+ words) should create successfully."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            "content": "word " * 20  # 100 chars, 20 words — well above limits
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 201
    assert response.json()["source_type"] == "text"


@pytest.mark.asyncio
async def test_create_text_content_source_too_few_words(client, episode_and_auth):
    """Text with <10 words (even if >= 50 chars) should return 422."""
    episode_id, headers = episode_and_auth

    # 5 long words, > 50 chars total
    content_data = {
        "episode_id": episode_id,
        "source_type": "text",
        "source_data": {
            "content": "superlongword " * 5
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    assert "word" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_validation_error_response_format(client, episode_and_auth):
    """422 error response should include a 'detail' field with meaningful text."""
    episode_id, headers = episode_and_auth

    content_data = {
        "episode_id": episode_id,
        "source_type": "url",
        "source_data": {
            "url": "ftp://bad-scheme.com",
            "title": "Bad"
        }
    }

    response = await client.post(
        f"/episodes/{episode_id}/content",
        headers=headers,
        json=content_data
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)
    assert len(body["detail"]) > 10  # Non-trivial message


# ============================================================================
# PDF UPLOAD ENDPOINT TESTS (#210)
# ============================================================================

def _pdf_upload_files(filename: str = "document.pdf", content_type: str = "application/pdf",
                      size_bytes: int = 2048):
    """Build a multipart 'files' payload for the PDF upload endpoint."""
    # Minimal PDF-ish bytes padded to the requested size.
    payload = b"%PDF-1.4\n" + b"0" * max(0, size_bytes - 9)
    return {"file": (filename, io.BytesIO(payload), content_type)}


@pytest.mark.asyncio
async def test_upload_pdf_success(client, episode_and_auth):
    """Uploading a valid PDF stores it and creates a 'pdf' content source."""
    episode_id, headers = episode_and_auth

    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ) as mock_s3, patch(
        "src.tasks.content_extraction.extract_content_task"
    ) as mock_task:
        mock_s3.return_value = "https://bucket.s3.amazonaws.com/content/key.pdf"
        response = await client.post(
            f"/episodes/{episode_id}/content/upload",
            headers=headers,
            files=_pdf_upload_files(),
            data={"description": "A test document", "auto_extract": "true"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["source_type"] == "pdf"
    assert data["extraction_status"] == "pending"
    # Record carries the S3 key + original filename + mime type
    assert data["source_data"]["filename"] == "document.pdf"
    assert data["source_data"]["mime_type"] == "application/pdf"
    assert data["source_data"]["s3_key"].startswith("content/")
    assert data["source_data"]["s3_key"].endswith("_document.pdf")
    # S3 upload was invoked with the same key recorded on the source
    mock_s3.assert_awaited_once()
    assert mock_s3.call_args[0][1] == data["source_data"]["s3_key"]
    # auto_extract=True dispatches the extraction task
    mock_task.delay.assert_called_once()
    assert mock_task.delay.call_args.kwargs["source_type"] == "pdf"


@pytest.mark.asyncio
async def test_upload_pdf_no_auto_extract(client, episode_and_auth):
    """auto_extract=false uploads without dispatching extraction."""
    episode_id, headers = episode_and_auth

    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ) as mock_s3, patch(
        "src.tasks.content_extraction.extract_content_task"
    ) as mock_task:
        mock_s3.return_value = None  # dev mode (no S3)
        response = await client.post(
            f"/episodes/{episode_id}/content/upload",
            headers=headers,
            files=_pdf_upload_files(),
            data={"auto_extract": "false"},
        )

    assert response.status_code == 201
    mock_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_upload_pdf_rejects_wrong_extension(client, episode_and_auth):
    """A non-.pdf filename is rejected with 422."""
    episode_id, headers = episode_and_auth

    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ):
        response = await client.post(
            f"/episodes/{episode_id}/content/upload",
            headers=headers,
            files=_pdf_upload_files(filename="notes.txt", content_type="text/plain"),
        )

    assert response.status_code == 422
    assert ".pdf" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_pdf_rejects_wrong_content_type(client, episode_and_auth):
    """A .pdf filename with a clearly non-PDF content type is rejected with 422."""
    episode_id, headers = episode_and_auth

    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ):
        response = await client.post(
            f"/episodes/{episode_id}/content/upload",
            headers=headers,
            files=_pdf_upload_files(filename="document.pdf", content_type="image/png"),
        )

    assert response.status_code == 422
    assert "content type" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_pdf_rejects_oversize(client, episode_and_auth):
    """A PDF larger than the 50MB limit is rejected with 413."""
    episode_id, headers = episode_and_auth

    from src.utils.validators import MAX_PDF_SIZE_BYTES

    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ):
        response = await client.post(
            f"/episodes/{episode_id}/content/upload",
            headers=headers,
            files=_pdf_upload_files(size_bytes=MAX_PDF_SIZE_BYTES + 1024),
        )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_pdf_episode_not_found(client, authenticated_headers):
    """Uploading to a non-existent episode returns 404."""
    missing_episode = uuid4()

    with patch(
        "src.services.content_service._upload_pdf_to_s3", new_callable=AsyncMock
    ):
        response = await client.post(
            f"/episodes/{missing_episode}/content/upload",
            headers=authenticated_headers,
            files=_pdf_upload_files(),
        )

    assert response.status_code == 404
