"""
Integration tests for RSS Feed Validation API endpoints.

Tests POST /projects/{project_id}/rss-feed/validate and
GET /projects/{project_id}/rss-feed/validation.
Covers authentication, tenant isolation, 404 cases, and result storage.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

VALID_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>A great podcast</description>
    <language>en-US</language>
    <lastBuildDate>Wed, 15 Jan 2025 10:30:00 +0000</lastBuildDate>
    <itunes:author>Test Author</itunes:author>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:image href="https://example.com/art.jpg"/>
    <item>
      <title>Episode 1</title>
      <description>Great episode</description>
      <pubDate>Wed, 15 Jan 2025 10:30:00 +0000</pubDate>
      <enclosure url="https://s3.example.com/ep1.mp3" length="5000000" type="audio/mpeg"/>
      <guid isPermaLink="false">episode-guid-001</guid>
      <itunes:duration>1800</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
    </item>
  </channel>
</rss>"""


def make_mock_rss_feed(project_id):
	"""Build a mock RSSFeed for patching service calls."""
	feed = MagicMock()
	feed.id = uuid4()
	feed.project_id = project_id
	feed.tenant_id = uuid4()
	feed.s3_key = f"rss-feeds/{project_id}/feed.xml"
	feed.public_url = f"https://bucket.s3.amazonaws.com/rss-feeds/{project_id}/feed.xml"
	feed.validation_status = {}
	feed.last_generated = datetime.now(timezone.utc)
	feed.created_at = datetime.now(timezone.utc)
	feed.updated_at = datetime.now(timezone.utc)
	return feed


def make_mock_validation_result(project_id):
	"""Build a mock ValidationStatusResponse dict for patching."""
	now = datetime.now(timezone.utc)
	directory_result = {
		"directory": "apple_podcasts",
		"valid": True,
		"errors": [],
		"warnings": [],
		"checked_at": now.isoformat(),
	}
	return {
		"last_validated_at": now.isoformat(),
		"apple_podcasts": {**directory_result, "directory": "apple_podcasts"},
		"spotify": {**directory_result, "directory": "spotify"},
		"google_podcasts": {**directory_result, "directory": "google_podcasts"},
		"is_valid_for_all": True,
	}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def project_with_metadata(client):
	"""Create user + project with podcast metadata; return (project_id, headers)."""
	reg = await client.post("/auth/register", json={
		"email": f"val_test_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Validation Tester",
	})
	assert reg.status_code == 201
	token = reg.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	proj = await client.post("/projects", headers=headers, json={
		"name": "Validation Test Project",
		"podcast_metadata": {
			"show_title": "Test Validation Podcast",
			"author": "Test Author",
			"description": "Testing RSS validation",
			"category": "Technology",
			"language": "en-US",
			"explicit": False,
		},
	})
	assert proj.status_code == 201
	return proj.json()["id"], headers


@pytest.fixture
async def second_user_headers(client):
	"""Create a second user (different tenant) and return auth headers."""
	reg = await client.post("/auth/register", json={
		"email": f"other_val_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Other Validation User",
	})
	assert reg.status_code == 201
	return {"Authorization": f"Bearer {reg.json()['access_token']}"}


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/rss-feed/validate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_rss_feed_success(client, project_with_metadata):
	"""Test successful validation returns full directory results."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)
	mock_result = make_mock_validation_result(project_id)

	from src.schemas.rss_feed import ValidationStatusResponse
	validation_response = ValidationStatusResponse(**mock_result)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen, \
	     patch("src.routers.rss_feed.RSSValidationService") as MockVal, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=VALID_RSS_XML)):
		mock_gen_inst = AsyncMock()
		mock_gen_inst.get_rss_feed.return_value = mock_feed
		MockGen.return_value = mock_gen_inst

		mock_val_inst = AsyncMock()
		mock_val_inst.validate_rss_feed.return_value = validation_response
		MockVal.return_value = mock_val_inst

		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert "last_validated_at" in data
	assert "apple_podcasts" in data
	assert "spotify" in data
	assert "google_podcasts" in data
	assert "is_valid_for_all" in data
	assert data["apple_podcasts"]["directory"] == "apple_podcasts"
	assert data["spotify"]["directory"] == "spotify"
	assert data["google_podcasts"]["directory"] == "google_podcasts"


@pytest.mark.asyncio
async def test_validate_rss_feed_requires_auth(client, project_with_metadata):
	"""Test that validate endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.post(f"/projects/{project_id}/rss-feed/validate")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_validate_rss_feed_project_not_found(client, project_with_metadata):
	"""Test 404 when project does not exist."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.post(
		f"/projects/{nonexistent_id}/rss-feed/validate",
		headers=headers,
	)
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_validate_rss_feed_no_feed_generated(client, project_with_metadata):
	"""Test 404 when feed has not been generated yet."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen:
		mock_gen_inst = AsyncMock()
		mock_gen_inst.get_rss_feed.return_value = None
		MockGen.return_value = mock_gen_inst

		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=headers,
		)

	assert response.status_code == 404
	assert "rss feed not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_validate_rss_feed_tenant_isolation(client, project_with_metadata, second_user_headers):
	"""Test that a user cannot validate another tenant's project."""
	project_id, _ = project_with_metadata

	response = await client.post(
		f"/projects/{project_id}/rss-feed/validate",
		headers=second_user_headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_validate_rss_feed_with_validation_errors(client, project_with_metadata):
	"""Test response includes errors when feed has issues."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)

	from datetime import datetime, timezone
	from src.schemas.rss_feed import (
		DirectoryValidationResult,
		ValidationError,
		ValidationStatusResponse,
	)

	now = datetime.now(timezone.utc)
	error = ValidationError(
		field="itunes:image",
		level="error",
		message="Artwork is 2000x2000. Minimum 3000x3000 required.",
	)
	bad_dir = DirectoryValidationResult(
		directory="spotify",
		valid=False,
		errors=[error],
		warnings=[],
		checked_at=now,
	)
	good_dir_apple = DirectoryValidationResult(
		directory="apple_podcasts",
		valid=True,
		errors=[],
		warnings=[],
		checked_at=now,
	)
	good_dir_google = DirectoryValidationResult(
		directory="google_podcasts",
		valid=True,
		errors=[],
		warnings=[],
		checked_at=now,
	)
	validation_response = ValidationStatusResponse(
		last_validated_at=now,
		apple_podcasts=good_dir_apple,
		spotify=bad_dir,
		google_podcasts=good_dir_google,
		is_valid_for_all=False,
	)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen, \
	     patch("src.routers.rss_feed.RSSValidationService") as MockVal, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=VALID_RSS_XML)):
		mock_gen_inst = AsyncMock()
		mock_gen_inst.get_rss_feed.return_value = mock_feed
		MockGen.return_value = mock_gen_inst

		mock_val_inst = AsyncMock()
		mock_val_inst.validate_rss_feed.return_value = validation_response
		MockVal.return_value = mock_val_inst

		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert data["is_valid_for_all"] is False
	assert data["spotify"]["valid"] is False
	assert len(data["spotify"]["errors"]) == 1
	assert data["spotify"]["errors"][0]["field"] == "itunes:image"
	assert data["spotify"]["errors"][0]["level"] == "error"


@pytest.mark.asyncio
async def test_validate_rss_feed_invalid_xml_returns_422(client, project_with_metadata):
	"""Test 422 when RSS XML cannot be parsed."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen, \
	     patch("src.routers.rss_feed.RSSValidationService") as MockVal, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=b"<broken")):
		mock_gen_inst = AsyncMock()
		mock_gen_inst.get_rss_feed.return_value = mock_feed
		MockGen.return_value = mock_gen_inst

		mock_val_inst = AsyncMock()
		mock_val_inst.validate_rss_feed.side_effect = ValueError("Invalid RSS XML: ...")
		MockVal.return_value = mock_val_inst

		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=headers,
		)

	assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/rss-feed/validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_validation_status_success(client, project_with_metadata):
	"""Test returning stored validation results."""
	project_id, headers = project_with_metadata

	mock_result = make_mock_validation_result(project_id)
	from src.schemas.rss_feed import ValidationStatusResponse
	validation_response = ValidationStatusResponse(**mock_result)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen, \
	     patch("src.routers.rss_feed.RSSValidationService") as MockVal:
		mock_gen_inst = AsyncMock()
		MockGen.return_value = mock_gen_inst

		mock_val_inst = AsyncMock()
		mock_val_inst.get_validation_status.return_value = validation_response
		MockVal.return_value = mock_val_inst

		response = await client.get(
			f"/projects/{project_id}/rss-feed/validation",
			headers=headers,
		)

	assert response.status_code == 200
	data = response.json()
	assert "last_validated_at" in data
	assert data["is_valid_for_all"] is True


@pytest.mark.asyncio
async def test_get_validation_status_requires_auth(client, project_with_metadata):
	"""Test that get validation endpoint requires authentication."""
	project_id, _ = project_with_metadata

	response = await client.get(f"/projects/{project_id}/rss-feed/validation")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_validation_status_project_not_found(client, project_with_metadata):
	"""Test 404 when project does not exist."""
	_, headers = project_with_metadata
	nonexistent_id = uuid4()

	response = await client.get(
		f"/projects/{nonexistent_id}/rss-feed/validation",
		headers=headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_validation_status_not_yet_validated(client, project_with_metadata):
	"""Test 404 when no validation results stored."""
	project_id, headers = project_with_metadata

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen, \
	     patch("src.routers.rss_feed.RSSValidationService") as MockVal:
		mock_gen_inst = AsyncMock()
		MockGen.return_value = mock_gen_inst

		mock_val_inst = AsyncMock()
		mock_val_inst.get_validation_status.return_value = None
		MockVal.return_value = mock_val_inst

		response = await client.get(
			f"/projects/{project_id}/rss-feed/validation",
			headers=headers,
		)

	assert response.status_code == 404
	assert "no validation results found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_validation_status_tenant_isolation(client, project_with_metadata, second_user_headers):
	"""Test that another tenant cannot access validation results."""
	project_id, _ = project_with_metadata

	response = await client.get(
		f"/projects/{project_id}/rss-feed/validation",
		headers=second_user_headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_validate_then_get_stores_results(client, project_with_metadata):
	"""Test that validate stores results retrievable by GET endpoint."""
	project_id, headers = project_with_metadata

	mock_feed = make_mock_rss_feed(project_id)
	mock_result = make_mock_validation_result(project_id)
	from src.schemas.rss_feed import ValidationStatusResponse
	validation_response = ValidationStatusResponse(**mock_result)

	with patch("src.routers.rss_feed.RSSGenerationService") as MockGen, \
	     patch("src.routers.rss_feed.RSSValidationService") as MockVal, \
	     patch("src.routers.rss_feed._fetch_rss_from_s3", new=AsyncMock(return_value=VALID_RSS_XML)):
		mock_gen_inst = AsyncMock()
		mock_gen_inst.get_rss_feed.return_value = mock_feed
		MockGen.return_value = mock_gen_inst

		mock_val_inst = AsyncMock()
		mock_val_inst.validate_rss_feed.return_value = validation_response
		mock_val_inst.get_validation_status.return_value = validation_response
		MockVal.return_value = mock_val_inst

		# POST to validate
		post_response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=headers,
		)
		assert post_response.status_code == 200

		# GET to retrieve stored results
		get_response = await client.get(
			f"/projects/{project_id}/rss-feed/validation",
			headers=headers,
		)
		assert get_response.status_code == 200

	post_data = post_response.json()
	get_data = get_response.json()
	assert post_data["is_valid_for_all"] == get_data["is_valid_for_all"]
