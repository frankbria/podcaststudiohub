"""
Integration tests for the episode audio download endpoint.

Tests the GET /episodes/{episode_id}/download endpoint including:
- Authentication requirements
- 404 when episode not found
- 403 when episode not complete or audio file missing
- 200 OK for full file download with correct headers
- 206 Partial Content for range requests
- 416 for invalid Range headers
"""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def episode_and_auth(client):
	"""Create user, project, and a complete episode with s3_key set."""
	# Register user
	reg_response = await client.post("/auth/register", json={
		"email": f"download_test_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Download Test User"
	})
	assert reg_response.status_code == 201
	token = reg_response.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	# Create project
	proj_response = await client.post("/projects", headers=headers, json={
		"name": "Download Test Project",
		"podcast_metadata": {
			"show_title": "Test Show",
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
			"title": "Download Test Episode",
			"description": "Episode for download testing"
		}
	})
	assert ep_response.status_code == 201
	episode_id = ep_response.json()["id"]

	# Update episode to "complete" status with s3_key and file_size_bytes
	update_response = await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"generation_status": "complete",
		"s3_key": f"podcasts/user-test/episode-{episode_id}.mp3",
		"s3_url": f"https://test-bucket.s3.amazonaws.com/podcasts/user-test/episode-{episode_id}.mp3",
		"file_size_bytes": 5242880
	})
	assert update_response.status_code == 200

	return episode_id, headers


def _mock_s3_storage(total_size: int, content: bytes, mock_class):
	"""Configure a mock StorageService for download tests."""
	mock_instance = MagicMock()
	mock_class.return_value = mock_instance
	mock_instance.bucket_name = "test-bucket"
	mock_instance.s3_client.head_object.return_value = {"ContentLength": total_size}
	mock_body = MagicMock()
	mock_body.read.side_effect = [content, b""]
	mock_instance.s3_client.get_object.return_value = {"Body": mock_body}
	return mock_instance


# ============================================================================
# Authentication tests
# ============================================================================

@pytest.mark.asyncio
async def test_download_requires_auth(client):
	"""Download endpoint requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/episodes/{fake_id}/download")
	assert response.status_code == 401


# ============================================================================
# Error cases
# ============================================================================

@pytest.mark.asyncio
async def test_download_episode_not_found(client, episode_and_auth):
	"""Returns 404 when episode ID doesn't exist."""
	_, headers = episode_and_auth
	fake_id = str(uuid4())

	response = await client.get(f"/episodes/{fake_id}/download", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_episode_not_complete(client, episode_and_auth):
	"""Returns 403 when episode is not in 'complete' status."""
	_, headers = episode_and_auth

	# Create a project and draft episode (not complete)
	proj_response = await client.post("/projects", headers=headers, json={
		"name": "Draft Project",
		"podcast_metadata": {
			"show_title": "Draft Show",
			"author": "Author",
			"description": "Desc"
		}
	})
	project_id = proj_response.json()["id"]

	ep_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Draft Ep", "description": "Desc"}
	})
	assert ep_response.status_code == 201
	draft_episode_id = ep_response.json()["id"]

	response = await client.get(f"/episodes/{draft_episode_id}/download", headers=headers)
	assert response.status_code == 403
	assert "not ready" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_download_episode_missing_s3_key(client, episode_and_auth):
	"""Returns 404 when episode is complete but s3_key is not set."""
	_, headers = episode_and_auth

	# Create a project and episode with complete status but no s3_key
	proj_response = await client.post("/projects", headers=headers, json={
		"name": "No S3 Project",
		"podcast_metadata": {
			"show_title": "No S3 Show",
			"author": "Author",
			"description": "Desc"
		}
	})
	project_id = proj_response.json()["id"]

	ep_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "No S3 Ep", "description": "Desc"}
	})
	episode_id = ep_response.json()["id"]

	# Mark complete without setting s3_key
	await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"generation_status": "complete"
	})

	response = await client.get(f"/episodes/{episode_id}/download", headers=headers)
	assert response.status_code == 404
	assert "audio file not found" in response.json()["detail"].lower()


# ============================================================================
# Successful full-file download
# ============================================================================

@pytest.mark.asyncio
async def test_download_full_file_success(client, episode_and_auth):
	"""Returns 200 with streaming response for full file download."""
	episode_id, headers = episode_and_auth
	fake_audio = b"FAKE_MP3_CONTENT_" * 10

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(len(fake_audio), fake_audio, MockStorage)
		response = await client.get(f"/episodes/{episode_id}/download", headers=headers)

	assert response.status_code == 200
	assert response.headers["content-type"] == "audio/mpeg"
	assert "attachment" in response.headers["content-disposition"]
	assert ".mp3" in response.headers["content-disposition"]
	assert response.headers["accept-ranges"] == "bytes"
	assert response.headers["cache-control"] == "private, max-age=31536000"


@pytest.mark.asyncio
async def test_download_content_disposition_filename(client, episode_and_auth):
	"""Content-Disposition header includes episode filename."""
	episode_id, headers = episode_and_auth

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(100, b"CONTENT", MockStorage)
		response = await client.get(f"/episodes/{episode_id}/download", headers=headers)

	assert response.status_code == 200
	content_disposition = response.headers["content-disposition"]
	assert "filename=" in content_disposition
	# Should include episode number and/or title
	assert "001" in content_disposition or "Download_Test_Episode" in content_disposition


@pytest.mark.asyncio
async def test_download_content_length_header(client, episode_and_auth):
	"""Content-Length header matches S3 file size."""
	episode_id, headers = episode_and_auth
	expected_size = 5242880

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(expected_size, b"DATA", MockStorage)
		response = await client.get(f"/episodes/{episode_id}/download", headers=headers)

	assert response.status_code == 200
	assert int(response.headers["content-length"]) == expected_size


@pytest.mark.asyncio
async def test_download_accept_ranges_header(client, episode_and_auth):
	"""Response includes Accept-Ranges: bytes header."""
	episode_id, headers = episode_and_auth

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(100, b"DATA", MockStorage)
		response = await client.get(f"/episodes/{episode_id}/download", headers=headers)

	assert response.headers["accept-ranges"] == "bytes"


# ============================================================================
# Range request tests
# ============================================================================

@pytest.mark.asyncio
async def test_download_range_request_206(client, episode_and_auth):
	"""Range request returns 206 Partial Content with Content-Range header."""
	episode_id, headers = episode_and_auth
	total_size = 5242880
	range_start, range_end = 0, 1023

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(total_size, b"X" * 1024, MockStorage)
		response = await client.get(
			f"/episodes/{episode_id}/download",
			headers={**headers, "Range": f"bytes={range_start}-{range_end}"}
		)

	assert response.status_code == 206
	assert response.headers["content-range"] == f"bytes {range_start}-{range_end}/{total_size}"
	assert int(response.headers["content-length"]) == 1024


@pytest.mark.asyncio
async def test_download_range_suffix(client, episode_and_auth):
	"""Suffix range 'bytes=-512' returns 206 with correct Content-Range."""
	episode_id, headers = episode_and_auth
	total_size = 5242880
	expected_start = total_size - 512

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(total_size, b"Y" * 512, MockStorage)
		response = await client.get(
			f"/episodes/{episode_id}/download",
			headers={**headers, "Range": "bytes=-512"}
		)

	assert response.status_code == 206
	expected_end = total_size - 1
	assert response.headers["content-range"] == f"bytes {expected_start}-{expected_end}/{total_size}"


@pytest.mark.asyncio
async def test_download_range_open_ended(client, episode_and_auth):
	"""Open-ended range 'bytes=1024-' returns 206 from 1024 to end."""
	episode_id, headers = episode_and_auth
	total_size = 2048
	range_start = 1024

	with patch("src.routers.episodes.StorageService") as MockStorage:
		_mock_s3_storage(total_size, b"Z" * 1024, MockStorage)
		response = await client.get(
			f"/episodes/{episode_id}/download",
			headers={**headers, "Range": f"bytes={range_start}-"}
		)

	assert response.status_code == 206
	expected_end = total_size - 1
	assert response.headers["content-range"] == f"bytes {range_start}-{expected_end}/{total_size}"


@pytest.mark.asyncio
async def test_download_invalid_range_returns_416(client, episode_and_auth):
	"""Invalid Range header (out of bounds) returns 416."""
	episode_id, headers = episode_and_auth
	total_size = 5242880

	with patch("src.routers.episodes.StorageService") as MockStorage:
		mock_instance = MagicMock()
		MockStorage.return_value = mock_instance
		mock_instance.bucket_name = "test-bucket"
		mock_instance.s3_client.head_object.return_value = {"ContentLength": total_size}

		# Range starting at or beyond total_size is invalid
		response = await client.get(
			f"/episodes/{episode_id}/download",
			headers={**headers, "Range": f"bytes={total_size}-{total_size + 100}"}
		)

	assert response.status_code == 416
