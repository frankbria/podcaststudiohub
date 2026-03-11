"""
Comprehensive test suite for RSS Feed Management API.

Tests generation, retrieval, update, and public access endpoints.
Covers authentication, tenant isolation, and 404/422 error cases.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ============================================================================
# SHARED FIXTURES
# ============================================================================

@pytest.fixture
async def project_with_metadata(client):
	"""Create user and project with full podcast metadata; return (project_id, headers)."""
	reg_response = await client.post("/auth/register", json={
		"email": f"rss_test_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "RSS Test User",
	})
	assert reg_response.status_code == 201
	token = reg_response.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	proj_response = await client.post("/projects", headers=headers, json={
		"name": "Test RSS Project",
		"podcast_metadata": {
			"show_title": "My Test Podcast",
			"author": "Test Author",
			"description": "A podcast for testing RSS generation",
			"category": "Technology",
			"language": "en-US",
			"explicit": False,
			"copyright": "© 2025 Test Author",
			"artwork_url": "https://example.com/art.jpg",
		},
	})
	assert proj_response.status_code == 201
	project_id = proj_response.json()["id"]

	return project_id, headers


@pytest.fixture
async def second_user_headers(client):
	"""Create a second user and return auth headers (different tenant)."""
	reg_response = await client.post("/auth/register", json={
		"email": f"other_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Other User",
	})
	assert reg_response.status_code == 201
	token = reg_response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


def make_mock_rss_feed(project_id):
	"""Build a mock RSSFeed object for patching service calls."""
	from datetime import datetime
	feed = MagicMock()
	feed.id = uuid4()
	feed.project_id = project_id
	feed.tenant_id = uuid4()
	feed.s3_key = f"rss-feeds/{project_id}/feed.xml"
	feed.public_url = f"https://bucket.s3.amazonaws.com/rss-feeds/{project_id}/feed.xml"
	feed.validation_status = {}
	feed.last_generated = datetime.utcnow()
	feed.created_at = datetime.utcnow()
	feed.updated_at = datetime.utcnow()
	return feed


# ============================================================================
# POST /projects/{project_id}/rss-feed/generate
# ============================================================================

@pytest.mark.asyncio
async def test_generate_rss_feed_success(client, project_with_metadata):
	"""Test successful RSS feed generation returns RSSFeed response."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.generate_rss_for_project.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.post(
			f"/projects/{project_id}/rss-feed/generate",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert data["project_id"] == str(project_id)
	assert "public_url" in data
	assert "s3_key" in data
	assert "last_generated" in data


@pytest.mark.asyncio
async def test_generate_rss_feed_project_not_found(client, project_with_metadata):
	"""Test 404 is returned when project does not exist."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.post(
		f"/projects/{nonexistent_id}/rss-feed/generate",
		headers=headers,
	)

	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_rss_feed_requires_auth(client, project_with_metadata):
	"""Test that generate endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.post(f"/projects/{project_id}/rss-feed/generate")

	assert response.status_code == 403


@pytest.mark.asyncio
async def test_generate_rss_feed_tenant_isolation(client, project_with_metadata, second_user_headers):
	"""Test that a user cannot generate feed for another tenant's project."""
	project_id, _ = project_with_metadata

	# Second user (different tenant) tries to generate feed for first user's project
	response = await client.post(
		f"/projects/{project_id}/rss-feed/generate",
		headers=second_user_headers,
	)

	# Should be 404 (RLS hides project, not 403)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_rss_feed_invalid_metadata(client, project_with_metadata):
	"""Test 422 when podcast_metadata missing required fields."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.generate_rss_for_project.side_effect = ValueError(
			"podcast_metadata missing required field: 'show_title'"
		)
		MockService.return_value = mock_instance

		response = await client.post(
			f"/projects/{project_id}/rss-feed/generate",
			headers=headers,
		)

	assert response.status_code == 422
	assert "show_title" in response.json()["detail"]


# ============================================================================
# GET /projects/{project_id}/rss-feed
# ============================================================================

@pytest.mark.asyncio
async def test_get_rss_feed_success(client, project_with_metadata):
	"""Test getting existing RSS feed returns metadata."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.get(
			f"/projects/{project_id}/rss-feed",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert data["project_id"] == str(project_id)
	assert "public_url" in data
	assert "last_generated" in data


@pytest.mark.asyncio
async def test_get_rss_feed_not_generated_yet(client, project_with_metadata):
	"""Test 404 when RSS feed has not been generated yet."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = None
		MockService.return_value = mock_instance

		response = await client.get(
			f"/projects/{project_id}/rss-feed",
			headers=headers,
		)

	assert response.status_code == 404
	assert "not generated yet" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_rss_feed_project_not_found(client, project_with_metadata):
	"""Test 404 when project does not exist."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.get(
		f"/projects/{nonexistent_id}/rss-feed",
		headers=headers,
	)

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_rss_feed_requires_auth(client, project_with_metadata):
	"""Test that get feed endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.get(f"/projects/{project_id}/rss-feed")

	assert response.status_code == 403


# ============================================================================
# PUT /projects/{project_id}/rss-feed
# ============================================================================

@pytest.mark.asyncio
async def test_update_rss_feed_success(client, project_with_metadata):
	"""Test updating metadata regenerates RSS feed."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.generate_rss_for_project.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.put(
			f"/projects/{project_id}/rss-feed",
			headers=headers,
			json={
				"podcast_metadata": {
					"show_title": "Updated Show Title",
					"category": "Science",
				}
			},
		)

	assert response.status_code == 200
	data = response.json()
	assert "public_url" in data


@pytest.mark.asyncio
async def test_update_rss_feed_project_not_found(client, project_with_metadata):
	"""Test 404 when updating feed for non-existent project."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.put(
		f"/projects/{nonexistent_id}/rss-feed",
		headers=headers,
		json={"podcast_metadata": {"show_title": "New Title"}},
	)

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_rss_feed_requires_auth(client, project_with_metadata):
	"""Test that update endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.put(
		f"/projects/{project_id}/rss-feed",
		json={"podcast_metadata": {"show_title": "New Title"}},
	)

	assert response.status_code == 403


# ============================================================================
# GET /feeds/{project_id}/podcast.xml (public endpoint)
# ============================================================================

@pytest.mark.asyncio
async def test_public_feed_success(client, project_with_metadata):
	"""Test public RSS feed returns valid XML without authentication."""
	project_id, _ = project_with_metadata

	sample_xml = b'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Test</title></channel></rss>'
	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=sample_xml)):
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		# No auth headers — public endpoint
		response = await client.get(f"/feeds/{project_id}/podcast.xml")

	assert response.status_code == 200
	assert "application/rss+xml" in response.headers["content-type"]
	assert b"<rss" in response.content


@pytest.mark.asyncio
async def test_public_feed_cache_headers(client, project_with_metadata):
	"""Test that public feed response includes Cache-Control header."""
	project_id, _ = project_with_metadata

	sample_xml = b'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>'
	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=sample_xml)):
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.get(f"/feeds/{project_id}/podcast.xml")

	assert response.status_code == 200
	assert "cache-control" in response.headers
	assert "max-age" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_public_feed_not_found_when_no_feed(client, project_with_metadata):
	"""Test 404 when RSS feed has not been generated."""
	project_id, _ = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = None
		MockService.return_value = mock_instance

		response = await client.get(f"/feeds/{project_id}/podcast.xml")

	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_public_feed_not_found_for_missing_project(client):
	"""Test 404 for completely non-existent project."""
	nonexistent_id = uuid4()

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = None
		MockService.return_value = mock_instance

		response = await client.get(f"/feeds/{nonexistent_id}/podcast.xml")

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_feed_accessible_without_jwt(client, project_with_metadata):
	"""Verify public endpoint does not require JWT (no Authorization header)."""
	project_id, _ = project_with_metadata

	sample_xml = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title></channel></rss>'
	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=sample_xml)):
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		# Explicitly no headers
		response = await client.get(
			f"/feeds/{project_id}/podcast.xml",
			headers={},
		)

	# Should succeed without auth
	assert response.status_code == 200


# ============================================================================
# POST /projects/{project_id}/rss-feed/validate
# ============================================================================

@pytest.mark.asyncio
async def test_trigger_rss_validation_success(client, project_with_metadata):
	"""Test that triggering validation returns 202 Accepted with task_id."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService"), \
	     patch("src.routers.rss_feed.generate_rss_feed_task") as mock_task:
		mock_async_result = MagicMock()
		mock_async_result.id = "test-task-id-12345"
		mock_task.delay.return_value = mock_async_result

		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=headers,
		)

	assert response.status_code == 202
	data = response.json()
	assert "task_id" in data
	assert data["status"] == "queued"
	assert "message" in data


@pytest.mark.asyncio
async def test_trigger_rss_validation_project_not_found(client, project_with_metadata):
	"""Test that triggering validation for non-existent project returns 404."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.post(
		f"/projects/{nonexistent_id}/rss-feed/validate",
		headers=headers,
	)

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_rss_validation_requires_auth(client, project_with_metadata):
	"""Test that validation trigger endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.post(f"/projects/{project_id}/rss-feed/validate")

	assert response.status_code == 403


# ============================================================================
# GET /projects/{project_id}/rss-feed/validation-status
# ============================================================================

@pytest.mark.asyncio
async def test_get_validation_status_success(client, project_with_metadata):
	"""Test getting validation status returns structured results."""
	project_id, headers = project_with_metadata
	from datetime import datetime

	mock_feed = make_mock_rss_feed(project_id)
	mock_feed.validation_status = {
		"last_validated_at": "2025-01-15T10:00:00+00:00",
		"apple_podcasts": {"valid": True, "errors": []},
		"spotify": {"valid": True, "errors": []},
		"google_podcasts": {"valid": True, "errors": []},
	}

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.get(
			f"/projects/{project_id}/rss-feed/validation-status",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert "apple_podcasts" in data
	assert "spotify" in data
	assert "google_podcasts" in data
	assert data["apple_podcasts"]["valid"] is True


@pytest.mark.asyncio
async def test_get_validation_status_feed_not_found(client, project_with_metadata):
	"""Test 404 when RSS feed has not been generated yet."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = None
		MockService.return_value = mock_instance

		response = await client.get(
			f"/projects/{project_id}/rss-feed/validation-status",
			headers=headers,
		)

	assert response.status_code == 404
	assert "not generated yet" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_validation_status_project_not_found(client, project_with_metadata):
	"""Test 404 when project does not exist."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.get(
		f"/projects/{nonexistent_id}/rss-feed/validation-status",
		headers=headers,
	)

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_validation_status_requires_auth(client, project_with_metadata):
	"""Test that validation-status endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.get(f"/projects/{project_id}/rss-feed/validation-status")

	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_validation_status_with_errors(client, project_with_metadata):
	"""Test validation status response when feed has errors."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)
	mock_feed.validation_status = {
		"last_validated_at": "2025-01-15T10:00:00+00:00",
		"apple_podcasts": {"valid": False, "errors": ["Missing itunes:image"]},
		"spotify": {"valid": True, "errors": []},
		"google_podcasts": {"valid": True, "errors": []},
	}

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.get(
			f"/projects/{project_id}/rss-feed/validation-status",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert data["apple_podcasts"]["valid"] is False
	assert "Missing itunes:image" in data["apple_podcasts"]["errors"]
