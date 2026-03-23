"""
Integration tests for quality metrics API endpoints.

Tests cover:
- GET /quality-metrics/episodes/{episode_id} - episode metrics retrieval
- GET /quality-metrics/projects/{project_id} - project aggregation
- GET /quality-metrics/projects/{project_id}/episodes - paginated episode list
- Authentication and tenant isolation
- 204 when metrics not calculated
- 404 for missing resources
- Sorting and pagination
"""

import pytest
from uuid import uuid4


# ============================================================================
# FIXTURES
# ============================================================================

SAMPLE_QUALITY_METRICS = {
	"total_words": 2450,
	"duration_estimate_minutes": 16.3,
	"coherence_score": 0.78,
	"tone": "casual",
	"speaker_balance_ratio": 1.2,
	"is_balanced": True,
	"max_monologue_words": 185,
	"dialogue_turns": 47,
	"has_good_banter": True,
}

POOR_QUALITY_METRICS = {
	"total_words": 300,
	"duration_estimate_minutes": 2.0,
	"coherence_score": 0.30,
	"tone": "academic",
	"speaker_balance_ratio": 5.0,
	"is_balanced": False,
	"max_monologue_words": 300,
	"dialogue_turns": 2,
	"has_good_banter": False,
}


@pytest.fixture
async def user_project_episode(client):
	"""Create user, project, and episode. Return (project_id, episode_id, headers)."""
	# Register user
	reg = await client.post("/auth/register", json={
		"email": f"qm_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "QM Test User",
	})
	assert reg.status_code == 201
	token = reg.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	# Create project
	proj = await client.post("/projects", headers=headers, json={
		"name": "QM Test Project",
		"podcast_metadata": {
			"show_title": "QM Show",
			"author": "QM Author",
			"description": "QM Description",
		},
	})
	assert proj.status_code == 201
	project_id = proj.json()["id"]

	# Create episode
	ep = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {
			"title": "Test Episode 1",
			"description": "First test episode",
		},
	})
	assert ep.status_code == 201
	episode_id = ep.json()["id"]

	return project_id, episode_id, headers


@pytest.fixture
async def episode_with_metrics(client, user_project_episode):
	"""Episode that has quality metrics stored in generation_progress."""
	project_id, episode_id, headers = user_project_episode

	# Inject quality metrics via episode update
	update = await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"generation_status": "complete",
		"generation_progress": {
			"stage": "complete",
			"progress": 100,
			"quality_metrics": SAMPLE_QUALITY_METRICS,
		},
	})
	assert update.status_code == 200

	return project_id, episode_id, headers


# ============================================================================
# GET /quality-metrics/episodes/{episode_id}
# ============================================================================

@pytest.mark.asyncio
async def test_get_episode_quality_metrics_success(client, episode_with_metrics):
	"""Test successful retrieval of episode quality metrics."""
	project_id, episode_id, headers = episode_with_metrics

	response = await client.get(
		f"/quality-metrics/episodes/{episode_id}",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()

	# Episode identity fields
	assert data["episode_id"] == episode_id
	assert data["episode_title"] == "Test Episode 1"
	assert data["episode_number"] == 1
	assert "calculated_at" in data

	# Raw metrics
	metrics = data["metrics"]
	assert metrics["total_words"] == 2450
	assert metrics["duration_estimate_minutes"] == 16.3
	assert metrics["coherence_score"] == 0.78
	assert metrics["tone"] == "casual"
	assert metrics["is_balanced"] is True
	assert metrics["has_good_banter"] is True

	# Quality scores
	assert len(data["quality_scores"]) == 5
	dimensions = {qs["dimension"] for qs in data["quality_scores"]}
	assert dimensions == {"content_length", "coherence", "balance", "engagement", "overall"}
	for qs in data["quality_scores"]:
		assert 0.0 <= qs["score"] <= 1.0
		assert qs["rating"] in {"poor", "fair", "good", "excellent"}

	# Interpretation
	interp = data["interpretation"]
	assert interp["overall_rating"] in {"poor", "fair", "good", "excellent"}
	assert isinstance(interp["strengths"], list)
	assert isinstance(interp["improvements"], list)
	assert interp["recommendations"] is not None


@pytest.mark.asyncio
async def test_get_episode_quality_metrics_not_calculated(client, user_project_episode):
	"""Test 204 No Content when quality metrics not yet calculated."""
	project_id, episode_id, headers = user_project_episode

	response = await client.get(
		f"/quality-metrics/episodes/{episode_id}",
		headers=headers,
	)
	assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_episode_quality_metrics_not_found(client, user_project_episode):
	"""Test 404 for non-existent episode."""
	project_id, episode_id, headers = user_project_episode
	fake_id = str(uuid4())

	response = await client.get(
		f"/quality-metrics/episodes/{fake_id}",
		headers=headers,
	)
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_episode_quality_metrics_unauthorized(client, episode_with_metrics):
	"""Test 401 without authentication."""
	project_id, episode_id, headers = episode_with_metrics

	response = await client.get(f"/quality-metrics/episodes/{episode_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_episode_quality_metrics_tenant_isolation(client, episode_with_metrics):
	"""Test that other users cannot access episodes from a different tenant."""
	project_id, episode_id, _ = episode_with_metrics

	# Register a different user (different tenant)
	reg2 = await client.post("/auth/register", json={
		"email": f"other_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Other User",
	})
	assert reg2.status_code == 201
	other_headers = {"Authorization": f"Bearer {reg2.json()['access_token']}"}

	response = await client.get(
		f"/quality-metrics/episodes/{episode_id}",
		headers=other_headers,
	)
	# Should be 404 because RLS hides cross-tenant data
	assert response.status_code == 404


# ============================================================================
# GET /quality-metrics/projects/{project_id}
# ============================================================================

@pytest.mark.asyncio
async def test_get_project_quality_metrics_no_episodes(client, user_project_episode):
	"""Test project quality metrics with no episodes having metrics."""
	project_id, episode_id, headers = user_project_episode

	response = await client.get(
		f"/quality-metrics/projects/{project_id}",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert data["project_id"] == project_id
	assert data["total_episodes_analyzed"] == 0
	assert data["quality_distribution"] == {"excellent": 0, "good": 0, "fair": 0, "poor": 0}


@pytest.mark.asyncio
async def test_get_project_quality_metrics_with_episodes(client, episode_with_metrics):
	"""Test project quality metrics aggregation with episodes that have metrics."""
	project_id, episode_id, headers = episode_with_metrics

	response = await client.get(
		f"/quality-metrics/projects/{project_id}",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()

	assert data["project_id"] == project_id
	assert data["total_episodes_analyzed"] == 1
	assert "date_range" in data
	assert "average_metrics" in data
	assert "quality_distribution" in data
	assert "quality_scores" in data
	assert "top_episodes" in data
	assert "worst_episodes" in data
	assert "trend" in data

	# Distribution should count exactly one episode
	total_in_dist = sum(data["quality_distribution"].values())
	assert total_in_dist == 1

	# Average metrics should match the single episode
	assert data["average_metrics"]["total_words"] == 2450

	# Trend with single episode should be stable
	assert data["trend"]["direction"] == "stable"


@pytest.mark.asyncio
async def test_get_project_quality_metrics_multiple_episodes(client, user_project_episode):
	"""Test aggregation with multiple episodes having different quality metrics."""
	project_id, episode_id, headers = user_project_episode

	# Update first episode with good metrics
	await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"generation_progress": {
			"stage": "complete",
			"quality_metrics": SAMPLE_QUALITY_METRICS,
		},
	})

	# Create a second episode with poor metrics
	ep2 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {
			"title": "Test Episode 2",
			"description": "Second test episode",
		},
	})
	ep2_id = ep2.json()["id"]
	await client.put(f"/episodes/{ep2_id}", headers=headers, json={
		"generation_progress": {
			"stage": "complete",
			"quality_metrics": POOR_QUALITY_METRICS,
		},
	})

	response = await client.get(
		f"/quality-metrics/projects/{project_id}",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()

	assert data["total_episodes_analyzed"] == 2
	# Total distribution entries should sum to 2
	assert sum(data["quality_distribution"].values()) == 2
	# Top/worst should be populated
	assert len(data["top_episodes"]) >= 1
	assert len(data["worst_episodes"]) >= 1


@pytest.mark.asyncio
async def test_get_project_quality_metrics_not_found(client, user_project_episode):
	"""Test 404 for non-existent project."""
	project_id, episode_id, headers = user_project_episode
	fake_id = str(uuid4())

	response = await client.get(
		f"/quality-metrics/projects/{fake_id}",
		headers=headers,
	)
	assert response.status_code == 404


# ============================================================================
# GET /quality-metrics/projects/{project_id}/episodes
# ============================================================================

@pytest.mark.asyncio
async def test_list_project_episode_metrics_empty(client, user_project_episode):
	"""Test listing episode metrics with no metrics available."""
	project_id, episode_id, headers = user_project_episode

	response = await client.get(
		f"/quality-metrics/projects/{project_id}/episodes",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert data["episodes"] == []
	assert data["page"] == 1
	assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_list_project_episode_metrics_with_data(client, episode_with_metrics):
	"""Test listing episode metrics returns proper structure."""
	project_id, episode_id, headers = episode_with_metrics

	response = await client.get(
		f"/quality-metrics/projects/{project_id}/episodes",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()

	assert data["total"] == 1
	assert len(data["episodes"]) == 1
	assert data["total_pages"] == 1

	ep = data["episodes"][0]
	assert ep["episode_id"] == episode_id
	assert "metrics" in ep
	assert "quality_scores" in ep
	assert "interpretation" in ep


@pytest.mark.asyncio
async def test_list_project_episode_metrics_pagination(client, user_project_episode):
	"""Test pagination parameters."""
	project_id, episode_id, headers = user_project_episode

	# Add metrics to episode 1
	await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"generation_progress": {
			"stage": "complete",
			"quality_metrics": SAMPLE_QUALITY_METRICS,
		},
	})

	# Create episodes 2 and 3 with metrics
	for i in range(2, 4):
		ep = await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {
				"title": f"Episode {i}",
				"description": f"Description {i}",
			},
		})
		await client.put(f"/episodes/{ep.json()['id']}", headers=headers, json={
			"generation_progress": {
				"stage": "complete",
				"quality_metrics": SAMPLE_QUALITY_METRICS,
			},
		})

	# Page 1 with page_size=2
	response = await client.get(
		f"/quality-metrics/projects/{project_id}/episodes?page=1&page_size=2",
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 3
	assert len(data["episodes"]) == 2
	assert data["page"] == 1
	assert data["page_size"] == 2
	assert data["total_pages"] == 2

	# Page 2 with page_size=2
	response2 = await client.get(
		f"/quality-metrics/projects/{project_id}/episodes?page=2&page_size=2",
		headers=headers,
	)
	assert response2.status_code == 200
	data2 = response2.json()
	assert len(data2["episodes"]) == 1
	assert data2["page"] == 2


@pytest.mark.asyncio
async def test_list_project_episode_metrics_sort_by_overall_score(client, user_project_episode):
	"""Test sorting by overall_score."""
	project_id, episode_id, headers = user_project_episode

	# Good episode
	await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"generation_progress": {
			"stage": "complete",
			"quality_metrics": SAMPLE_QUALITY_METRICS,
		},
	})

	# Poor episode
	ep2 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {
			"title": "Poor Episode",
			"description": "Poor quality",
		},
	})
	await client.put(f"/episodes/{ep2.json()['id']}", headers=headers, json={
		"generation_progress": {
			"stage": "complete",
			"quality_metrics": POOR_QUALITY_METRICS,
		},
	})

	# Sort descending by overall_score (best first)
	response = await client.get(
		f"/quality-metrics/projects/{project_id}/episodes?sort_by=overall_score&order=desc",
		headers=headers,
	)
	assert response.status_code == 200
	episodes = response.json()["episodes"]
	assert len(episodes) == 2

	# Better episode should come first
	scores = [
		next(qs["score"] for qs in ep["quality_scores"] if qs["dimension"] == "overall")
		for ep in episodes
	]
	assert scores[0] >= scores[1]


@pytest.mark.asyncio
async def test_list_project_episode_metrics_sort_by_duration(client, episode_with_metrics):
	"""Test sorting by duration is accepted."""
	project_id, episode_id, headers = episode_with_metrics

	response = await client.get(
		f"/quality-metrics/projects/{project_id}/episodes?sort_by=duration&order=asc",
		headers=headers,
	)
	assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_project_episode_metrics_not_found(client, user_project_episode):
	"""Test 404 for non-existent project."""
	project_id, episode_id, headers = user_project_episode
	fake_id = str(uuid4())

	response = await client.get(
		f"/quality-metrics/projects/{fake_id}/episodes",
		headers=headers,
	)
	assert response.status_code == 404
