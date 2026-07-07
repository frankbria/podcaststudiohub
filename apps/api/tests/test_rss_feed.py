"""
Comprehensive test suite for RSS Feed Management API.

Tests generation, retrieval, update, and public access endpoints.
Covers authentication, tenant isolation, and 404/422 error cases.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.routers.rss_feed import _fetch_rss_from_s3, get_rss_service
from src.services.rss_generation_service import RSSGenerationService


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

	assert response.status_code == 401


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


@pytest.mark.asyncio
async def test_generate_rss_feed_internal_error_hides_details(client, project_with_metadata):
	"""500 from an unexpected error returns a generic message, not exception internals."""
	project_id, headers = project_with_metadata
	secret = "boto3 AccessDenied arn:aws:s3:::secret-bucket"

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.generate_rss_for_project.side_effect = RuntimeError(secret)
		MockService.return_value = mock_instance

		response = await client.post(
			f"/projects/{project_id}/rss-feed/generate",
			headers=headers,
		)

	assert response.status_code == 500
	assert response.json()["detail"] == "Failed to generate RSS feed."
	assert secret not in response.text


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

	assert response.status_code == 401


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

	assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_rss_feed_invalid_metadata(client, project_with_metadata):
	"""Test 422 when regeneration fails because merged metadata is missing required fields."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.generate_rss_for_project.side_effect = ValueError(
			"podcast_metadata missing required field: 'author'"
		)
		MockService.return_value = mock_instance

		response = await client.put(
			f"/projects/{project_id}/rss-feed",
			headers=headers,
			json={"podcast_metadata": {"show_title": "New Title"}},
		)

	assert response.status_code == 422
	assert "author" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_rss_feed_internal_error_hides_details(client, project_with_metadata):
	"""500 during regeneration returns a generic message, not exception internals."""
	project_id, headers = project_with_metadata
	secret = "psycopg constraint rss_feeds_pkey violated"

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService:
		mock_instance = AsyncMock()
		mock_instance.generate_rss_for_project.side_effect = RuntimeError(secret)
		MockService.return_value = mock_instance

		response = await client.put(
			f"/projects/{project_id}/rss-feed",
			headers=headers,
			json={"podcast_metadata": {"show_title": "New Title"}},
		)

	assert response.status_code == 500
	assert response.json()["detail"] == "Failed to regenerate RSS feed."
	assert secret not in response.text


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
async def test_public_feed_internal_error_hides_details(client, project_with_metadata):
	"""500 while fetching from S3 returns a generic message, not exception internals."""
	project_id, _ = project_with_metadata
	secret = "S3 NoSuchKey rss-feeds/internal/path.xml"
	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockService, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(side_effect=RuntimeError(secret))):
		mock_instance = AsyncMock()
		mock_instance.get_rss_feed.return_value = mock_feed
		MockService.return_value = mock_instance

		response = await client.get(f"/feeds/{project_id}/podcast.xml")

	assert response.status_code == 500
	assert response.json()["detail"] == "Failed to fetch RSS feed."
	assert secret not in response.text


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
# Dependency provider / internal helper unit tests
#
# get_rss_service is a *synchronous* FastAPI dependency, so when it is
# resolved through a live HTTP request it runs inside Starlette's
# threadpool executor and is invisible to coverage (.coveragerc only
# configures `concurrency = greenlet`, not `thread`). Call it directly here
# so it executes on the main test thread.
# ============================================================================

def test_get_rss_service_returns_service_instance():
	"""get_rss_service() should construct a fresh RSSGenerationService."""
	service = get_rss_service()

	assert isinstance(service, RSSGenerationService)


@pytest.mark.asyncio
async def test_fetch_rss_from_s3_downloads_and_reads_file():
	"""_fetch_rss_from_s3 should download the S3 object to a temp file, read
	its bytes, and clean up the temp file afterwards."""
	xml_bytes = b'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>'

	async def fake_download_file(s3_key, local_path):
		with open(local_path, "wb") as f:
			f.write(xml_bytes)
		return local_path

	rss_service = MagicMock()
	rss_service.storage.download_file = AsyncMock(side_effect=fake_download_file)

	result = await _fetch_rss_from_s3(rss_service, "rss-feeds/some-project/feed.xml")

	assert result == xml_bytes
	rss_service.storage.download_file.assert_awaited_once()
