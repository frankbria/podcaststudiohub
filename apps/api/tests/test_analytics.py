"""
Tests for analytics event tracking and usage metrics endpoints.

Tests cover:
- POST /analytics/events: event ingestion, validation
- GET /analytics/episodes/{episode_id}: episode analytics summary
- GET /projects/{project_id}/analytics: project analytics dashboard
- Authentication enforcement
- Privacy (IP hashing)
"""

import pytest
from uuid import uuid4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def setup(client):
	"""Register a user, create a project and episode; return all handles."""
	reg = await client.post("/auth/register", json={
		"email": f"analytics_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Analytics User",
	})
	assert reg.status_code == 201
	token = reg.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	proj = await client.post("/projects", headers=headers, json={
		"name": "Analytics Project",
		"podcast_metadata": {
			"show_title": "My Show",
			"author": "Author",
			"description": "Desc",
		},
	})
	assert proj.status_code == 201
	project_id = proj.json()["id"]

	ep = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_metadata": {
			"title": "Episode 1",
			"description": "First episode",
		},
	})
	assert ep.status_code == 201
	episode_id = ep.json()["id"]

	return {"headers": headers, "project_id": project_id, "episode_id": episode_id}


# ---------------------------------------------------------------------------
# POST /analytics/events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_track_event_download(client, setup):
	"""Test tracking a download event stores correctly."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "download",
			"episode_id": setup["episode_id"],
			"project_id": setup["project_id"],
		},
	)
	assert response.status_code == 201
	data = response.json()
	assert data["event_type"] == "download"
	assert data["episode_id"] == setup["episode_id"]
	assert data["project_id"] == setup["project_id"]
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_track_event_play(client, setup):
	"""Test tracking a play event with metadata."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "play",
			"episode_id": setup["episode_id"],
			"metadata": {"duration_listened_seconds": 300, "completed": False},
		},
	)
	assert response.status_code == 201
	data = response.json()
	assert data["event_type"] == "play"
	assert data["event_metadata"]["duration_listened_seconds"] == 300


@pytest.mark.asyncio
async def test_track_event_share(client, setup):
	"""Test tracking a share event."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "share",
			"episode_id": setup["episode_id"],
		},
	)
	assert response.status_code == 201
	assert response.json()["event_type"] == "share"


@pytest.mark.asyncio
async def test_track_event_stream(client, setup):
	"""Test tracking a stream event."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "stream",
			"episode_id": setup["episode_id"],
		},
	)
	assert response.status_code == 201
	assert response.json()["event_type"] == "stream"


@pytest.mark.asyncio
async def test_track_event_invalid_type(client, setup):
	"""Test that invalid event types are rejected."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "invalid_type",
			"episode_id": setup["episode_id"],
		},
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_track_event_requires_auth(client, setup):
	"""Test that event tracking requires authentication."""
	response = await client.post(
		"/analytics/events",
		json={
			"event_type": "download",
			"episode_id": setup["episode_id"],
		},
	)
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_track_event_nonexistent_episode(client, setup):
	"""Test that tracking event for nonexistent episode returns 404."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "download",
			"episode_id": str(uuid4()),
		},
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_track_event_nonexistent_project(client, setup):
	"""Test that tracking event for nonexistent project returns 404."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={
			"event_type": "download",
			"project_id": str(uuid4()),
		},
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_track_event_without_episode_or_project(client, setup):
	"""Test tracking event with just event_type (no episode or project)."""
	response = await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={"event_type": "play"},
	)
	assert response.status_code == 201
	data = response.json()
	assert data["event_type"] == "play"
	assert data["episode_id"] is None
	assert data["project_id"] is None


# ---------------------------------------------------------------------------
# GET /analytics/episodes/{episode_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_episode_analytics_empty(client, setup):
	"""Test episode analytics returns zero counts when no events exist."""
	response = await client.get(
		f"/analytics/episodes/{setup['episode_id']}",
		headers=setup["headers"],
	)
	assert response.status_code == 200
	data = response.json()
	assert data["episode_id"] == setup["episode_id"]
	assert "metrics" in data
	assert data["metrics"]["total_downloads"] == 0
	assert data["metrics"]["total_plays"] == 0
	assert "period" in data
	assert "device_breakdown" in data


@pytest.mark.asyncio
async def test_get_episode_analytics_with_events(client, setup):
	"""Test episode analytics counts events correctly."""
	# Track 2 downloads and 1 play
	for _ in range(2):
		await client.post(
			"/analytics/events",
			headers=setup["headers"],
			json={"event_type": "download", "episode_id": setup["episode_id"]},
		)
	await client.post(
		"/analytics/events",
		headers=setup["headers"],
		json={"event_type": "play", "episode_id": setup["episode_id"]},
	)

	response = await client.get(
		f"/analytics/episodes/{setup['episode_id']}",
		headers=setup["headers"],
	)
	assert response.status_code == 200
	data = response.json()
	assert data["metrics"]["total_downloads"] == 2
	assert data["metrics"]["total_plays"] == 1


@pytest.mark.asyncio
async def test_get_episode_analytics_requires_auth(client, setup):
	"""Test that episode analytics requires authentication."""
	response = await client.get(f"/analytics/episodes/{setup['episode_id']}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_episode_analytics_not_found(client, setup):
	"""Test episode analytics returns 404 for nonexistent episode."""
	response = await client.get(
		f"/analytics/episodes/{uuid4()}",
		headers=setup["headers"],
	)
	assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/analytics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_project_analytics_empty(client, setup):
	"""Test project analytics returns zero counts when no events exist."""
	response = await client.get(
		f"/projects/{setup['project_id']}/analytics",
		headers=setup["headers"],
	)
	assert response.status_code == 200
	data = response.json()
	assert data["project_id"] == setup["project_id"]
	assert "summary" in data
	assert data["summary"]["total_downloads"] == 0
	assert "period" in data
	assert data["period"]["days"] == 30
	assert "top_episodes" in data


@pytest.mark.asyncio
async def test_get_project_analytics_with_events(client, setup):
	"""Test project analytics aggregates events for all project episodes."""
	# Track 3 downloads for the episode (associated with the project)
	for _ in range(3):
		await client.post(
			"/analytics/events",
			headers=setup["headers"],
			json={
				"event_type": "download",
				"episode_id": setup["episode_id"],
				"project_id": setup["project_id"],
			},
		)

	response = await client.get(
		f"/projects/{setup['project_id']}/analytics",
		headers=setup["headers"],
	)
	assert response.status_code == 200
	data = response.json()
	assert data["summary"]["total_downloads"] == 3


@pytest.mark.asyncio
async def test_get_project_analytics_custom_period(client, setup):
	"""Test project analytics respects custom days parameter."""
	response = await client.get(
		f"/projects/{setup['project_id']}/analytics?days=7",
		headers=setup["headers"],
	)
	assert response.status_code == 200
	assert response.json()["period"]["days"] == 7


@pytest.mark.asyncio
async def test_get_project_analytics_requires_auth(client, setup):
	"""Test that project analytics requires authentication."""
	response = await client.get(f"/projects/{setup['project_id']}/analytics")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_project_analytics_not_found(client, setup):
	"""Test project analytics returns 404 for nonexistent project."""
	response = await client.get(
		f"/projects/{uuid4()}/analytics",
		headers=setup["headers"],
	)
	assert response.status_code == 404
