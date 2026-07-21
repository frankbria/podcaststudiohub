"""
Integration tests for analytics endpoints (GAP-049).
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from src.models.analytics_event import AnalyticsEvent


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


async def register_and_login_with_tenant(client, email=None):
	"""Register a new user and return (auth headers, tenant_id)."""
	if email is None:
		email = f"test_{uuid4()}@example.com"
	response = await client.post("/auth/register", json={
		"email": email,
		"password": "SecurePass123!",
		"full_name": "Test User",
	})
	assert response.status_code == 201, response.text
	body = response.json()
	headers = {"Authorization": f"Bearer {body['access_token']}"}
	return headers, UUID(body["user"]["tenant_id"])


async def _seed_event(test_db, tenant_id, event_type, *, episode_id=None,
                      project_id=None, created_at=None, metadata=None):
	"""Insert an AnalyticsEvent directly on the shared test session.

	The track endpoint now queues the insert to Celery (issue #322), so
	round-trip aggregation tests seed events directly instead of POSTing.
	Relies on RLS tenant context already armed on `test_db` by a preceding API
	request (register/create project/episode) — same pattern as
	test_analytics_aggregation.py.
	"""
	from src.utils.datetime_utils import utcnow
	event = AnalyticsEvent(
		tenant_id=UUID(str(tenant_id)),
		episode_id=UUID(str(episode_id)) if episode_id else None,
		project_id=UUID(str(project_id)) if project_id else None,
		event_type=event_type,
		event_metadata=metadata,
		created_at=created_at or utcnow(),
	)
	test_db.add(event)
	await test_db.commit()


async def create_project(client, headers):
	"""Create a project and return its ID."""
	response = await client.post("/projects", json={
		"name": f"Test Project {uuid4()}",
		"description": "Analytics test project",
		"podcast_metadata": {
			"show_title": "Analytics Test Show",
			"author": "Test Author",
			"description": "Analytics test project",
		},
	}, headers=headers)
	assert response.status_code == 201, response.text
	return response.json()["id"]


async def create_episode(client, headers, project_id):
	"""Create an episode and return its ID."""
	response = await client.post("/episodes", json={
		"project_id": project_id,
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


@pytest.mark.asyncio
async def test_track_event_queues_task_with_payload(client):
	"""Track queues the insert (off the request path) with the full payload (#322).

	The 201 response is built from the in-process payload — the same id/
	created_at the task will persist — so no DB write/refresh happens inline.
	"""
	headers, tenant_id = await register_and_login_with_tenant(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	with patch("src.tasks.analytics.track_analytics_event_task") as mock_task:
		response = await client.post("/analytics/events", json={
			"event_type": "play",
			"episode_id": episode_id,
			"project_id": project_id,
			"metadata": {"completed": True},
		}, headers=headers)

	assert response.status_code == 201, response.text
	data = response.json()
	mock_task.delay.assert_called_once()
	payload = mock_task.delay.call_args.kwargs["payload"]
	assert payload["id"] == data["id"]
	assert payload["tenant_id"] == str(tenant_id)
	assert payload["event_type"] == "play"
	assert payload["episode_id"] == episode_id
	assert payload["project_id"] == project_id
	assert payload["event_metadata"] == {"completed": True}


@pytest.mark.asyncio
async def test_track_event_threads_country_header_into_payload(client):
	"""CF-IPCountry header is read at the boundary and queued on the payload (#325)."""
	headers = await register_and_login(client)
	headers["CF-IPCountry"] = "gb"
	with patch("src.tasks.analytics.track_analytics_event_task") as mock_task:
		response = await client.post("/analytics/events", json={
			"event_type": "download",
		}, headers=headers)
	assert response.status_code == 201, response.text
	payload = mock_task.delay.call_args.kwargs["payload"]
	assert payload["country"] == "GB"  # normalized


@pytest.mark.asyncio
async def test_track_event_x_country_fallback(client):
	"""X-Country is the fallback when CF-IPCountry is absent (#325)."""
	headers = await register_and_login(client)
	headers["X-Country"] = "US"
	with patch("src.tasks.analytics.track_analytics_event_task") as mock_task:
		response = await client.post("/analytics/events", json={
			"event_type": "download",
		}, headers=headers)
	assert response.status_code == 201, response.text
	assert mock_task.delay.call_args.kwargs["payload"]["country"] == "US"


@pytest.mark.asyncio
async def test_track_event_broker_down_still_returns_201(client):
	"""A broker outage must never fail the request — analytics are best-effort."""
	headers = await register_and_login(client)
	with patch("src.tasks.analytics.track_analytics_event_task") as mock_task:
		mock_task.delay.side_effect = RuntimeError("broker unavailable")
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
async def test_get_episode_analytics_counts_correctly(client, test_db):
	"""Episode analytics should count events correctly."""
	headers, tenant_id = await register_and_login_with_tenant(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	# Seed 2 downloads, 1 play (track insert is now async off the request path).
	for _ in range(2):
		await _seed_event(test_db, tenant_id, "download", episode_id=episode_id)
	await _seed_event(test_db, tenant_id, "play", episode_id=episode_id)

	response = await client.get(f"/analytics/episodes/{episode_id}", headers=headers)
	assert response.status_code == 200, response.text
	data = response.json()
	assert data["metrics"]["total_downloads"] == 2
	assert data["metrics"]["total_plays"] == 1


@pytest.mark.asyncio
async def test_get_episode_analytics_tz_aware_date_range(client, test_db):
	"""Z-suffixed (TZ-aware) date params must not raise against naive created_at (#310)."""
	headers, tenant_id = await register_and_login_with_tenant(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	await _seed_event(test_db, tenant_id, "download", episode_id=episode_id)

	date_from = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
	date_to = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
	response = await client.get(
		f"/analytics/episodes/{episode_id}?date_from={date_from}&date_to={date_to}",
		headers=headers,
	)
	assert response.status_code == 200, response.text
	assert response.json()["metrics"]["total_downloads"] == 1


@pytest.mark.asyncio
async def test_get_episode_analytics_non_utc_offset_converted(client, test_db):
	"""Non-UTC offsets must be converted to UTC, not just tz-stripped (#310)."""
	headers, tenant_id = await register_and_login_with_tenant(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	await _seed_event(test_db, tenant_id, "download", episode_id=episode_id)

	# 30 min ago UTC, expressed in +03:00 — naive stripping would yield a
	# wall time ~2.5h in the future and wrongly exclude the event just tracked.
	plus3 = timezone(timedelta(hours=3))
	date_from = (datetime.now(timezone.utc) - timedelta(minutes=30)).astimezone(plus3)
	response = await client.get(
		f"/analytics/episodes/{episode_id}",
		params={"date_from": date_from.isoformat()},
		headers=headers,
	)
	assert response.status_code == 200, response.text
	assert response.json()["metrics"]["total_downloads"] == 1


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
async def test_get_project_analytics_aggregates_correctly(client, test_db):
	"""Project analytics should aggregate events from all episodes."""
	headers, tenant_id = await register_and_login_with_tenant(client)
	project_id = await create_project(client, headers)
	episode_id = await create_episode(client, headers, project_id)

	# Seed 3 downloads for the project (track insert is now async off-request).
	for _ in range(3):
		await _seed_event(test_db, tenant_id, "download",
		                  episode_id=episode_id, project_id=project_id)

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
