"""
Integration tests for analytics endpoints (GAP-049).
"""

import pytest
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def register_and_login(client, email=None):
	"""Register a new user and return auth headers."""
	if email is None:
		email = f"test_{uuid4()}@example.com"
	response = await client.post("/auth/register", json={
		"email": email,
		"password": "SecurePass123!",
		"full_name": "Test User",
	})
	assert response.status_code == 201, response.text
	token = response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


async def create_project(client, headers):
	"""Create a project and return its ID."""
	response = await client.post("/projects", json={
		"name": f"Test Project {uuid4()}",
		"description": "Analytics test project",
	}, headers=headers)
	assert response.status_code == 201, response.text
	return response.json()["id"]


async def create_episode(client, headers, project_id):
	"""Create an episode and return its ID."""
	response = await client.post(f"/projects/{project_id}/episodes", json={
		"episode_metadata": {
			"title": f"Test Episode {uuid4()}",
			"description": "Test",
		},
	}, headers=headers)
	assert response.status_code == 201, response.text
	return response.json()["id"]


# ---------------------------------------------------------------------------
# Authentication guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_event_requires_auth(client):
	"""POST /analytics/events requires authentication."""
	response = await client.post("/analytics/events", json={
		"event_type": "play",
	})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_episode_analytics_requires_auth(client):
	"""GET /analytics/episodes/{id} requires authentication."""
	response = await client.get(f"/analytics/episodes/{uuid4()}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_project_analytics_requires_auth(client):
	"""GET /projects/{id}/analytics requires authentication."""
	response = await client.get(f"/projects/{uuid4()}/analytics")
	assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /analytics/events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_play_event_returns_201(client):
	"""Tracking a play event should return 201 with event data."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	response = await client.post("/analytics/events", json={
		"event_type": "play",
		"episode_id": episode_id,
		"project_id": project_id,
	}, headers=headers)
	assert response.status_code == 201, response.text
	data = response.json()
	assert data["event_type"] == "play"
	assert data["episode_id"] == episode_id
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_track_download_event(client):
	"""Tracking a download event should succeed."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	response = await client.post("/analytics/events", json={
		"event_type": "download",
		"episode_id": episode_id,
	}, headers=headers)
	assert response.status_code == 201, response.text
	assert response.json()["event_type"] == "download"


@pytest.mark.asyncio
async def test_track_event_with_metadata(client):
	"""Tracking an event with metadata stores the metadata."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	response = await client.post("/analytics/events", json={
		"event_type": "play",
		"episode_id": episode_id,
		"metadata": {"duration_listened_seconds": 300, "completed": False},
	}, headers=headers)
	assert response.status_code == 201, response.text
	data = response.json()
	assert data["event_metadata"]["duration_listened_seconds"] == 300


@pytest.mark.asyncio
async def test_track_event_invalid_type_returns_422(client):
	"""Invalid event_type should return 422 Unprocessable Entity."""
	headers = await register_and_login(client)
	response = await client.post("/analytics/events", json={
		"event_type": "invalid_event",
	}, headers=headers)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_track_event_nonexistent_episode_returns_404(client):
	"""Tracking event for nonexistent episode should return 404."""
	headers = await register_and_login(client)
	response = await client.post("/analytics/events", json={
		"event_type": "play",
		"episode_id": str(uuid4()),
	}, headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_track_event_nonexistent_project_returns_404(client):
	"""Tracking event for nonexistent project should return 404."""
	headers = await register_and_login(client)
	response = await client.post("/analytics/events", json={
		"event_type": "download",
		"project_id": str(uuid4()),
	}, headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_track_event_without_episode_or_project(client):
	"""Tracking an event with no episode_id or project_id should succeed."""
	headers = await register_and_login(client)
	response = await client.post("/analytics/events", json={
		"event_type": "share",
	}, headers=headers)
	assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# GET /analytics/episodes/{episode_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_episode_analytics_zero_counts(client):
	"""Episode with no events should return zero counts."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	response = await client.get(f"/analytics/episodes/{episode_id}", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert data["metrics"]["total_downloads"] == 0
	assert data["metrics"]["total_plays"] == 0
	assert data["episode_id"] == episode_id


@pytest.mark.asyncio
async def test_get_episode_analytics_counts_correctly(client):
	"""Episode analytics should count events correctly."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	# Track 2 downloads, 1 play
	for _ in range(2):
		await client.post("/analytics/events", json={
			"event_type": "download",
			"episode_id": episode_id,
		}, headers=headers)
	await client.post("/analytics/events", json={
		"event_type": "play",
		"episode_id": episode_id,
	}, headers=headers)

	response = await client.get(f"/analytics/episodes/{episode_id}", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert data["metrics"]["total_downloads"] == 2
	assert data["metrics"]["total_plays"] == 1


@pytest.mark.asyncio
async def test_get_episode_analytics_nonexistent_returns_404(client):
	"""Analytics for a nonexistent episode should return 404."""
	headers = await register_and_login(client)
	response = await client.get(f"/analytics/episodes/{uuid4()}", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_episode_analytics_has_device_breakdown(client):
	"""Episode analytics response includes device_breakdown."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	response = await client.get(f"/analytics/episodes/{episode_id}", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert "device_breakdown" in data
	assert "app_breakdown" in data
	assert "top_countries" in data


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/analytics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_project_analytics_zero_counts(client):
	"""Project with no events should return zero summary counts."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)

	response = await client.get(f"/projects/{project_id}/analytics", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert data["summary"]["total_downloads"] == 0
	assert data["summary"]["total_plays"] == 0
	assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_get_project_analytics_aggregates_correctly(client):
	"""Project analytics should aggregate events from all episodes."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	# Track 3 downloads for project
	for _ in range(3):
		await client.post("/analytics/events", json={
			"event_type": "download",
			"episode_id": episode_id,
			"project_id": project_id,
		}, headers=headers)

	response = await client.get(f"/projects/{project_id}/analytics", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert data["summary"]["total_downloads"] == 3


@pytest.mark.asyncio
async def test_get_project_analytics_nonexistent_returns_404(client):
	"""Analytics for a nonexistent project should return 404."""
	headers = await register_and_login(client)
	response = await client.get(f"/projects/{uuid4()}/analytics", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_project_analytics_has_trends(client):
	"""Project analytics response includes trends and top_episodes."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)

	response = await client.get(f"/projects/{project_id}/analytics", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert "trends" in data
	assert "weekly_downloads" in data["trends"]
	assert "top_episodes" in data
	assert "period" in data


@pytest.mark.asyncio
async def test_get_project_analytics_custom_days_param(client):
	"""GET /projects/{id}/analytics?days=7 uses specified period."""
	headers = await register_and_login(client)
	project_id = await create_project(client, headers)

	response = await client.get(f"/projects/{project_id}/analytics?days=7", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert data["period"]["days"] == 7
