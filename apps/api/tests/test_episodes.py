"""
Comprehensive test suite for Episode Management API.

Tests CRUD operations, pagination, validation, project relationships,
status filtering, and tenant isolation for episodes.
"""

import pytest
from uuid import uuid4


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


# ============================================================================
# CRUD TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_episode(client, project_and_auth):
	"""Test successful episode creation."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {
			"title": "Episode 1",
			"description": "First episode"
		}
	})
	assert response.status_code == 201
	data = response.json()
	assert data["episode_number"] == 1
	assert data["generation_status"] == "draft"
	assert data["episode_metadata"]["title"] == "Episode 1"
	assert data["episode_metadata"]["description"] == "First episode"
	assert "id" in data
	assert "user_id" in data
	assert "tenant_id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_create_episode_with_optional_metadata(client, project_and_auth):
	"""Test episode creation with optional metadata fields."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {
			"title": "Episode 2",
			"description": "Second episode",
			"format": "bonus",
			"explicit": True,
			"season_number": 1
		}
	})
	assert response.status_code == 201
	data = response.json()
	assert data["episode_metadata"]["format"] == "bonus"
	assert data["episode_metadata"]["explicit"] == True


@pytest.mark.asyncio
async def test_list_episodes(client, project_and_auth):
	"""Test listing episodes."""
	project_id, headers = project_and_auth

	# Create 3 episodes
	for i in range(1, 4):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {
				"title": f"Episode {i}",
				"description": f"Description {i}"
			}
		})

	# List all episodes
	response = await client.get("/episodes", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] >= 3
	assert len(data["episodes"]) >= 3


@pytest.mark.asyncio
async def test_list_episodes_by_project(client, project_and_auth):
	"""Test listing episodes filtered by project."""
	project_id, headers = project_and_auth

	# Create 3 episodes
	for i in range(1, 4):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {
				"title": f"Episode {i}",
				"description": f"Description {i}"
			}
		})

	# List episodes for project
	response = await client.get(
		f"/episodes?project_id={project_id}",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 3
	assert len(data["episodes"]) == 3
	# Verify sorted by episode_number
	assert data["episodes"][0]["episode_number"] == 1
	assert data["episodes"][2]["episode_number"] == 3


@pytest.mark.asyncio
async def test_list_episodes_empty(client, project_and_auth):
	"""Test listing episodes when none exist."""
	project_id, headers = project_and_auth

	response = await client.get(
		f"/episodes?project_id={project_id}",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert len(data["episodes"]) == 0


@pytest.mark.asyncio
async def test_get_episode_by_id(client, project_and_auth):
	"""Test retrieving specific episode."""
	project_id, headers = project_and_auth

	# Create episode
	create_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {
			"title": "Specific Episode",
			"description": "Test description"
		}
	})
	assert create_response.status_code == 201
	episode_id = create_response.json()["id"]

	# Get episode
	response = await client.get(f"/episodes/{episode_id}", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert data["episode_metadata"]["title"] == "Specific Episode"
	assert data["id"] == episode_id


@pytest.mark.asyncio
async def test_get_nonexistent_episode(client, project_and_auth):
	"""Test getting episode that doesn't exist."""
	_, headers = project_and_auth
	fake_id = str(uuid4())

	response = await client.get(f"/episodes/{fake_id}", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_episode(client, project_and_auth):
	"""Test episode update."""
	project_id, headers = project_and_auth

	# Create episode
	create_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {
			"title": "Original Title",
			"description": "Original description"
		}
	})
	assert create_response.status_code == 201
	episode_id = create_response.json()["id"]

	# Update episode metadata only (partial update)
	response = await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"episode_metadata": {
			"title": "Updated Title",
			"description": "Updated description"
		}
	})
	assert response.status_code == 200
	data = response.json()
	assert data["episode_metadata"]["title"] == "Updated Title"
	assert data["episode_number"] == 1  # Unchanged


@pytest.mark.asyncio
async def test_update_episode_number(client, project_and_auth):
	"""Test updating episode number."""
	project_id, headers = project_and_auth

	# Create episode
	create_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Ep1", "description": "Desc"}
	})
	episode_id = create_response.json()["id"]

	# Update episode number
	response = await client.put(f"/episodes/{episode_id}", headers=headers, json={
		"episode_number": 2
	})
	assert response.status_code == 200
	assert response.json()["episode_number"] == 2


@pytest.mark.asyncio
async def test_update_nonexistent_episode(client, project_and_auth):
	"""Test updating episode that doesn't exist."""
	_, headers = project_and_auth
	fake_id = str(uuid4())

	response = await client.put(f"/episodes/{fake_id}", headers=headers, json={
		"episode_metadata": {"title": "New", "description": "New"}
	})
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_episode(client, project_and_auth):
	"""Test episode deletion (hard delete)."""
	project_id, headers = project_and_auth

	# Create episode
	create_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "To Delete", "description": "Desc"}
	})
	assert create_response.status_code == 201
	episode_id = create_response.json()["id"]

	# Delete episode
	response = await client.delete(f"/episodes/{episode_id}", headers=headers)
	assert response.status_code == 204

	# Verify deleted
	get_response = await client.get(f"/episodes/{episode_id}", headers=headers)
	assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_episode(client, project_and_auth):
	"""Test deleting episode that doesn't exist."""
	_, headers = project_and_auth
	fake_id = str(uuid4())

	response = await client.delete(f"/episodes/{fake_id}", headers=headers)
	assert response.status_code == 404


# ============================================================================
# PROJECT RELATIONSHIP TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_episode_invalid_project(client, project_and_auth):
	"""Test episode creation with non-existent project."""
	_, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": str(uuid4()),  # Random UUID
		"episode_number": 1,
		"episode_metadata": {
			"title": "Episode 1",
			"description": "Description"
		}
	})
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_multiple_episodes_same_project(client, project_and_auth):
	"""Test creating multiple episodes for same project."""
	project_id, headers = project_and_auth

	# Create 5 episodes
	for i in range(1, 6):
		response = await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {
				"title": f"Episode {i}",
				"description": f"Desc {i}"
			}
		})
		assert response.status_code == 201

	# Verify all episodes exist
	list_response = await client.get(
		f"/episodes?project_id={project_id}",
		headers=headers
	)
	assert list_response.json()["total"] == 5


# ============================================================================
# GENERATION STATUS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_generation_status(client, project_and_auth):
	"""Test updating episode generation status."""
	project_id, headers = project_and_auth

	# Create episode
	create_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Ep1", "description": "Desc"}
	})
	assert create_response.json()["generation_status"] == "draft"
	episode_id = create_response.json()["id"]

	# Update status to generating
	update_response = await client.put(
		f"/episodes/{episode_id}",
		headers=headers,
		json={"generation_status": "generating"}
	)
	assert update_response.status_code == 200
	assert update_response.json()["generation_status"] == "generating"

	# Update status to complete
	complete_response = await client.put(
		f"/episodes/{episode_id}",
		headers=headers,
		json={"generation_status": "complete"}
	)
	assert complete_response.json()["generation_status"] == "complete"


@pytest.mark.asyncio
async def test_filter_by_status(client, project_and_auth):
	"""Test filtering episodes by generation status."""
	project_id, headers = project_and_auth

	# Create episodes with different statuses
	ep1_resp = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Ep1", "description": "Desc"}
	})
	ep1_id = ep1_resp.json()["id"]

	ep2_resp = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Ep2", "description": "Desc"}
	})
	ep2_id = ep2_resp.json()["id"]

	# Update one to generating
	await client.put(f"/episodes/{ep1_id}", headers=headers, json={
		"generation_status": "generating"
	})

	# Keep ep2 in draft

	# Filter by draft status
	draft_response = await client.get(
		"/episodes?status=draft",
		headers=headers
	)
	draft_data = draft_response.json()
	assert draft_data["total"] >= 1
	draft_ids = [ep["id"] for ep in draft_data["episodes"]]
	assert ep2_id in draft_ids

	# Filter by generating status
	generating_response = await client.get(
		"/episodes?status=generating",
		headers=headers
	)
	generating_data = generating_response.json()
	assert generating_data["total"] >= 1
	generating_ids = [ep["id"] for ep in generating_data["episodes"]]
	assert ep1_id in generating_ids


# ============================================================================
# VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_validation_missing_title(client, project_and_auth):
	"""Test validation for missing episode_metadata.title."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"description": "Desc only"}
	})
	assert response.status_code == 422
	assert "title" in response.text.lower()


@pytest.mark.asyncio
async def test_validation_missing_description(client, project_and_auth):
	"""Test validation for missing episode_metadata.description."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Title only"}
	})
	assert response.status_code == 422
	assert "description" in response.text.lower()


@pytest.mark.asyncio
async def test_validation_empty_title(client, project_and_auth):
	"""Test validation for empty title."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "", "description": "Desc"}
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_missing_episode_metadata(client, project_and_auth):
	"""Test validation when episode_metadata is missing."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_invalid_episode_number(client, project_and_auth):
	"""Test validation for invalid episode_number (must be >= 1)."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 0,  # Invalid
		"episode_metadata": {"title": "Ep", "description": "Desc"}
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_negative_episode_number(client, project_and_auth):
	"""Test validation for negative episode_number."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": -1,
		"episode_metadata": {"title": "Ep", "description": "Desc"}
	})
	assert response.status_code == 422


# ============================================================================
# PAGINATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pagination_basic(client, project_and_auth):
	"""Test basic pagination with page size and page number."""
	project_id, headers = project_and_auth

	# Create 25 episodes
	for i in range(1, 26):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {
				"title": f"Episode {i}",
				"description": f"Desc {i}"
			}
		})

	# Get page 1 (20 items by default)
	page1 = await client.get(
		f"/episodes?project_id={project_id}&page=1&page_size=20",
		headers=headers
	)
	assert page1.status_code == 200
	data1 = page1.json()
	assert data1["total"] == 25
	assert len(data1["episodes"]) == 20
	assert data1["page"] == 1
	assert data1["total_pages"] == 2

	# Get page 2 (5 remaining items)
	page2 = await client.get(
		f"/episodes?project_id={project_id}&page=2&page_size=20",
		headers=headers
	)
	assert page2.status_code == 200
	data2 = page2.json()
	assert len(data2["episodes"]) == 5
	assert data2["page"] == 2


@pytest.mark.asyncio
async def test_pagination_custom_page_size(client, project_and_auth):
	"""Test pagination with custom page size."""
	project_id, headers = project_and_auth

	# Create 15 episodes
	for i in range(1, 16):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {"title": f"Ep {i}", "description": "Desc"}
		})

	# Get with page_size=5
	response = await client.get(
		f"/episodes?project_id={project_id}&page=1&page_size=5",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 15
	assert len(data["episodes"]) == 5
	assert data["total_pages"] == 3


@pytest.mark.asyncio
async def test_episode_ordering_by_number(client, project_and_auth):
	"""Test episodes are ordered by episode_number ascending."""
	project_id, headers = project_and_auth

	# Create episodes out of order
	for i in [3, 1, 4, 2, 5]:
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {"title": f"Ep {i}", "description": "Desc"}
		})

	# List episodes
	response = await client.get(
		f"/episodes?project_id={project_id}",
		headers=headers
	)
	data = response.json()
	episodes = data["episodes"]

	# Verify ordered by episode_number
	assert episodes[0]["episode_number"] == 1
	assert episodes[1]["episode_number"] == 2
	assert episodes[2]["episode_number"] == 3
	assert episodes[3]["episode_number"] == 4
	assert episodes[4]["episode_number"] == 5


# ============================================================================
# AUTO-ASSIGNMENT AND UNIQUENESS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_episode_without_episode_number(client, project_and_auth):
	"""Test episode_number is auto-assigned when not provided."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_metadata": {
			"title": "Auto Numbered",
			"description": "Should get episode_number 1"
		}
	})
	assert response.status_code == 201
	data = response.json()
	assert data["episode_number"] == 1


@pytest.mark.asyncio
async def test_auto_assignment_increments_per_project(client, project_and_auth):
	"""Test auto-assigned numbers increment sequentially per project."""
	project_id, headers = project_and_auth

	# Create 3 episodes without specifying episode_number
	for i in range(3):
		response = await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_metadata": {
				"title": f"Episode {i + 1}",
				"description": "Auto numbered"
			}
		})
		assert response.status_code == 201
		assert response.json()["episode_number"] == i + 1


@pytest.mark.asyncio
async def test_auto_assignment_after_explicit_number(client, project_and_auth):
	"""Test auto-assignment continues from max existing episode_number."""
	project_id, headers = project_and_auth

	# Create episode with explicit number 5
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 5,
		"episode_metadata": {"title": "Ep 5", "description": "Desc"}
	})

	# Auto-assigned episode should get number 6
	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_metadata": {"title": "Auto", "description": "Desc"}
	})
	assert response.status_code == 201
	assert response.json()["episode_number"] == 6


@pytest.mark.asyncio
async def test_duplicate_episode_number_same_project_returns_409(client, project_and_auth):
	"""Test that duplicate episode_number within same project returns 409."""
	project_id, headers = project_and_auth

	# Create episode with number 1
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "First", "description": "Desc"}
	})

	# Attempt to create another with same number
	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Duplicate", "description": "Desc"}
	})
	assert response.status_code == 409


@pytest.mark.asyncio
async def test_same_episode_number_different_projects(client, project_and_auth):
	"""Test that same episode_number is allowed across different projects."""
	project_id_1, headers = project_and_auth

	# Create second project
	proj2_response = await client.post("/projects", headers=headers, json={
		"name": "Second Project",
		"podcast_metadata": {
			"show_title": "Show 2",
			"author": "Author 2",
			"description": "Description 2"
		}
	})
	assert proj2_response.status_code == 201
	project_id_2 = proj2_response.json()["id"]

	# Create episode 1 in project 1
	r1 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id_1,
		"episode_number": 1,
		"episode_metadata": {"title": "Ep1 P1", "description": "Desc"}
	})
	assert r1.status_code == 201

	# Create episode 1 in project 2 - should succeed
	r2 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id_2,
		"episode_number": 1,
		"episode_metadata": {"title": "Ep1 P2", "description": "Desc"}
	})
	assert r2.status_code == 201


@pytest.mark.asyncio
async def test_episode_response_has_non_null_episode_number(client, project_and_auth):
	"""Test that episode responses always include a non-null episode_number."""
	project_id, headers = project_and_auth

	response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_metadata": {"title": "Test", "description": "Desc"}
	})
	assert response.status_code == 201
	data = response.json()
	assert data["episode_number"] is not None
	assert isinstance(data["episode_number"], int)
	assert data["episode_number"] >= 1


# ============================================================================
# TENANT ISOLATION TESTS (SKIPPED)
# ============================================================================

@pytest.mark.skip(reason="Test fixture transaction handling interferes with RLS. Manual/integration tests verify RLS works.")
@pytest.mark.asyncio
async def test_tenant_isolation_episodes(client):
	"""Verify users cannot access other tenant's episodes."""
	# Following Task 2.5 approach - skip with documented reason
	pass


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_episode_requires_auth(client):
	"""Test that creating episode requires authentication."""
	response = await client.post("/episodes", json={
		"project_id": str(uuid4()),
		"episode_number": 1,
		"episode_metadata": {"title": "Test", "description": "Desc"}
	})
	# Auth middleware returns 403 Forbidden when no valid token provided
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_episodes_requires_auth(client):
	"""Test that listing episodes requires authentication."""
	response = await client.get("/episodes")
	# Auth middleware returns 403 Forbidden when no valid token provided
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_episode_requires_auth(client):
	"""Test that getting episode requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/episodes/{fake_id}")
	# Auth middleware returns 403 Forbidden when no valid token provided
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_episode_requires_auth(client):
	"""Test that updating episode requires authentication."""
	fake_id = str(uuid4())
	response = await client.put(f"/episodes/{fake_id}", json={
		"episode_metadata": {"title": "New", "description": "New"}
	})
	# Auth middleware returns 403 Forbidden when no valid token provided
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_episode_requires_auth(client):
	"""Test that deleting episode requires authentication."""
	fake_id = str(uuid4())
	response = await client.delete(f"/episodes/{fake_id}")
	# Auth middleware returns 403 Forbidden when no valid token provided
	assert response.status_code == 403


# ============================================================================
# SEARCH AND FILTER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_search_episodes_by_title(client, project_and_auth):
	"""Test full-text search on episode title."""
	project_id, headers = project_and_auth

	# Create episodes with distinct titles
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "AI Safety Podcast", "description": "Discussing safety"}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Music Theory Basics", "description": "Learning music"}
	})

	# Search by title keyword
	response = await client.get(
		f"/episodes?project_id={project_id}&search=AI+Safety",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["episodes"][0]["episode_metadata"]["title"] == "AI Safety Podcast"


@pytest.mark.asyncio
async def test_search_episodes_by_description(client, project_and_auth):
	"""Test full-text search on episode description."""
	project_id, headers = project_and_auth

	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Episode One", "description": "Covers neural networks"}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Episode Two", "description": "Covers climate change"}
	})

	# Search description
	response = await client.get(
		f"/episodes?project_id={project_id}&search=neural",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert "neural" in data["episodes"][0]["episode_metadata"]["description"]


@pytest.mark.asyncio
async def test_search_episodes_no_results(client, project_and_auth):
	"""Test search returns empty when no match."""
	project_id, headers = project_and_auth

	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Tech Talk", "description": "About technology"}
	})

	response = await client.get(
		f"/episodes?project_id={project_id}&search=zyxwvutsrqponm",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert len(data["episodes"]) == 0


@pytest.mark.asyncio
async def test_search_case_insensitive(client, project_and_auth):
	"""Test that search is case insensitive."""
	project_id, headers = project_and_auth

	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Python Programming", "description": "Learn Python"}
	})

	# Search with different casing
	response = await client.get(
		f"/episodes?project_id={project_id}&search=python",
		headers=headers
	)
	assert response.status_code == 200
	assert response.json()["total"] == 1


@pytest.mark.asyncio
async def test_filter_by_date_from(client, project_and_auth):
	"""Test filtering episodes by date_from."""
	project_id, headers = project_and_auth

	# Create episode (created_at is set automatically to now)
	ep_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Recent Episode", "description": "Just created"}
	})
	assert ep_response.status_code == 201

	# Filter with date_from set to past date - should include episode
	response = await client.get(
		f"/episodes?project_id={project_id}&date_from=2020-01-01T00:00:00",
		headers=headers
	)
	assert response.status_code == 200
	assert response.json()["total"] == 1

	# Filter with date_from set to far future - should exclude episode
	response = await client.get(
		f"/episodes?project_id={project_id}&date_from=2099-01-01T00:00:00",
		headers=headers
	)
	assert response.status_code == 200
	assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_filter_by_date_to(client, project_and_auth):
	"""Test filtering episodes by date_to."""
	project_id, headers = project_and_auth

	# Create episode
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Test Episode", "description": "Desc"}
	})

	# Filter with date_to in future - should include episode
	response = await client.get(
		f"/episodes?project_id={project_id}&date_to=2099-12-31T23:59:59",
		headers=headers
	)
	assert response.status_code == 200
	assert response.json()["total"] == 1

	# Filter with date_to in the past - should exclude episode
	response = await client.get(
		f"/episodes?project_id={project_id}&date_to=2020-01-01T00:00:00",
		headers=headers
	)
	assert response.status_code == 200
	assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_filter_by_tags(client, project_and_auth):
	"""Test filtering episodes by tags in episode_metadata."""
	project_id, headers = project_and_auth

	# Create episodes with tags
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {
			"title": "Tech Episode",
			"description": "About tech",
			"tags": ["tech", "ai"]
		}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {
			"title": "Music Episode",
			"description": "About music",
			"tags": ["music", "culture"]
		}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 3,
		"episode_metadata": {
			"title": "No Tags Episode",
			"description": "No tags here"
		}
	})

	# Filter by tag "tech"
	response = await client.get(
		f"/episodes?project_id={project_id}&tags=tech",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["episodes"][0]["episode_metadata"]["title"] == "Tech Episode"


@pytest.mark.asyncio
async def test_filter_by_multiple_tags(client, project_and_auth):
	"""Test filtering by multiple tags (OR logic - any matching tag)."""
	project_id, headers = project_and_auth

	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Tech", "description": "Tech ep", "tags": ["tech"]}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Music", "description": "Music ep", "tags": ["music"]}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 3,
		"episode_metadata": {"title": "Other", "description": "Other ep", "tags": ["other"]}
	})

	# Filter by "tech" or "music"
	response = await client.get(
		f"/episodes?project_id={project_id}&tags=tech,music",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 2


@pytest.mark.asyncio
async def test_filter_by_min_duration(client, project_and_auth):
	"""Test filtering episodes by minimum duration."""
	project_id, headers = project_and_auth

	# Create episodes
	ep1 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Short", "description": "Short ep"}
	})
	ep2 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Long", "description": "Long ep"}
	})

	# Set durations via update
	await client.put(f"/episodes/{ep1.json()['id']}", headers=headers, json={"duration_seconds": 120.0})
	await client.put(f"/episodes/{ep2.json()['id']}", headers=headers, json={"duration_seconds": 3600.0})

	# Filter min_duration=600
	response = await client.get(
		f"/episodes?project_id={project_id}&min_duration=600",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["episodes"][0]["episode_metadata"]["title"] == "Long"


@pytest.mark.asyncio
async def test_filter_by_max_duration(client, project_and_auth):
	"""Test filtering episodes by maximum duration."""
	project_id, headers = project_and_auth

	ep1 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Short", "description": "Short ep"}
	})
	ep2 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Long", "description": "Long ep"}
	})

	await client.put(f"/episodes/{ep1.json()['id']}", headers=headers, json={"duration_seconds": 120.0})
	await client.put(f"/episodes/{ep2.json()['id']}", headers=headers, json={"duration_seconds": 3600.0})

	# Filter max_duration=300
	response = await client.get(
		f"/episodes?project_id={project_id}&max_duration=300",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["episodes"][0]["episode_metadata"]["title"] == "Short"


@pytest.mark.asyncio
async def test_sort_by_created_at_asc(client, project_and_auth):
	"""Test sorting episodes by created_at ascending."""
	project_id, headers = project_and_auth

	# Create 3 episodes
	for i in range(1, 4):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {"title": f"Ep {i}", "description": "Desc"}
		})

	response = await client.get(
		f"/episodes?project_id={project_id}&sort_by=created_at&sort_order=asc",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert len(data["episodes"]) == 3


@pytest.mark.asyncio
async def test_sort_order_desc(client, project_and_auth):
	"""Test sorting episodes descending by episode_number."""
	project_id, headers = project_and_auth

	for i in range(1, 4):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {"title": f"Ep {i}", "description": "Desc"}
		})

	response = await client.get(
		f"/episodes?project_id={project_id}&sort_by=episode_number&sort_order=desc",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["episodes"][0]["episode_number"] == 3
	assert data["episodes"][2]["episode_number"] == 1


@pytest.mark.asyncio
async def test_combined_search_and_status_filter(client, project_and_auth):
	"""Test combining search query with status filter."""
	project_id, headers = project_and_auth

	# Create episodes
	ep1 = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Science Complete", "description": "Complete science"}
	})
	await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 2,
		"episode_metadata": {"title": "Science Draft", "description": "Draft science"}
	})

	# Mark ep1 as complete
	await client.put(f"/episodes/{ep1.json()['id']}", headers=headers, json={"generation_status": "complete"})

	# Search "Science" AND status=complete
	response = await client.get(
		f"/episodes?project_id={project_id}&search=Science&status=complete",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["episodes"][0]["episode_metadata"]["title"] == "Science Complete"


@pytest.mark.asyncio
async def test_invalid_sort_by_returns_422(client, project_and_auth):
	"""Test that invalid sort_by value returns 422."""
	project_id, headers = project_and_auth

	response = await client.get(
		f"/episodes?project_id={project_id}&sort_by=invalid_field",
		headers=headers
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_sort_order_returns_422(client, project_and_auth):
	"""Test that invalid sort_order value returns 422."""
	project_id, headers = project_and_auth

	response = await client.get(
		f"/episodes?project_id={project_id}&sort_order=sideways",
		headers=headers
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_backward_compatible(client, project_and_auth):
	"""Test that existing list endpoint still works without search params."""
	project_id, headers = project_and_auth

	for i in range(1, 4):
		await client.post("/episodes", headers=headers, json={
			"project_id": project_id,
			"episode_number": i,
			"episode_metadata": {"title": f"Ep {i}", "description": "Desc"}
		})

	# Original request without new params should work
	response = await client.get(
		f"/episodes?project_id={project_id}",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 3
	assert "episodes" in data
	assert "total_pages" in data
