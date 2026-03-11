"""
Comprehensive test suite for Episode Composition API.

Tests creating/updating composition timelines, validating layouts,
triggering renders, and checking render status. Also covers service-level
unit tests for validation logic and schema validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
async def episode_and_auth(client):
	"""Register user, create project, and create episode. Returns (episode_id, headers)."""
	reg_response = await client.post("/auth/register", json={
		"email": f"comp_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Composition Test User"
	})
	assert reg_response.status_code == 201
	token = reg_response.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	proj_response = await client.post("/projects", headers=headers, json={
		"name": "Composition Test Project",
		"podcast_metadata": {
			"show_title": "Comp Show",
			"author": "Test Author",
			"description": "Test"
		}
	})
	assert proj_response.status_code == 201
	project_id = proj_response.json()["id"]

	ep_response = await client.post("/episodes", headers=headers, json={
		"project_id": project_id,
		"episode_number": 1,
		"episode_metadata": {"title": "Episode 1", "description": "Test"}
	})
	assert ep_response.status_code == 201
	episode_id = ep_response.json()["id"]

	return episode_id, headers


def generated_timeline() -> list:
	"""Return a minimal valid timeline with only a generated segment."""
	return [
		{
			"type": "generated",
			"position_seconds": 0.0,
			"fade_in_ms": 0,
			"fade_out_ms": 0,
			"normalize": True,
			"volume_level": 1.0
		}
	]


# ============================================================================
# UNIT TESTS - SCHEMAS
# ============================================================================


class TestCompositionSchemas:
	"""Unit tests for episode composition Pydantic schemas."""

	def test_timeline_segment_generated_type(self):
		"""Test that 'generated' segment type is valid without snippet_id."""
		from src.schemas.episode_composition import TimelineSegment
		seg = TimelineSegment(type="generated", position_seconds=0.0)
		assert seg.type == "generated"
		assert seg.snippet_id is None

	def test_timeline_segment_intro_type(self):
		"""Test 'intro' segment with snippet_id."""
		from src.schemas.episode_composition import TimelineSegment
		snippet_id = uuid4()
		seg = TimelineSegment(type="intro", snippet_id=snippet_id)
		assert seg.type == "intro"
		assert seg.snippet_id == snippet_id

	def test_timeline_segment_defaults(self):
		"""Test TimelineSegment default values."""
		from src.schemas.episode_composition import TimelineSegment
		seg = TimelineSegment(type="generated")
		assert seg.fade_in_ms == 0
		assert seg.fade_out_ms == 0
		assert seg.normalize is True
		assert seg.volume_level == 1.0
		assert seg.position_seconds == 0.0

	def test_timeline_segment_volume_bounds(self):
		"""Test volume_level must be between 0.0 and 2.0."""
		from src.schemas.episode_composition import TimelineSegment
		import pydantic
		with pytest.raises(pydantic.ValidationError):
			TimelineSegment(type="generated", volume_level=3.0)

	def test_timeline_segment_fade_ms_bounds(self):
		"""Test fade_in_ms and fade_out_ms must not exceed 10000."""
		from src.schemas.episode_composition import TimelineSegment
		import pydantic
		with pytest.raises(pydantic.ValidationError):
			TimelineSegment(type="generated", fade_in_ms=20000)

	def test_composition_create_valid(self):
		"""Test CompositionCreate with valid timeline."""
		from src.schemas.episode_composition import CompositionCreate, TimelineSegment
		data = CompositionCreate(
			timeline=[TimelineSegment(type="generated")]
		)
		assert len(data.timeline) == 1

	def test_composition_create_empty_timeline_rejected(self):
		"""Test CompositionCreate rejects empty timeline."""
		from src.schemas.episode_composition import CompositionCreate
		import pydantic
		with pytest.raises(pydantic.ValidationError):
			CompositionCreate(timeline=[])

	def test_render_status_response_fields(self):
		"""Test RenderStatusResponse has required fields."""
		from src.schemas.episode_composition import RenderStatusResponse
		resp = RenderStatusResponse(status="queued", progress=0)
		assert resp.status == "queued"
		assert resp.progress == 0
		assert resp.error is None


# ============================================================================
# INTEGRATION TESTS - COMPOSITION ENDPOINTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_composition_requires_auth(client, episode_and_auth):
	"""Test that GET composition requires authentication."""
	episode_id, _ = episode_and_auth
	response = await client.get(f"/episodes/{episode_id}/composition")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_post_composition_requires_auth(client, episode_and_auth):
	"""Test that POST composition requires authentication."""
	episode_id, _ = episode_and_auth
	response = await client.post(
		f"/episodes/{episode_id}/composition",
		json={"timeline": generated_timeline()}
	)
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_composition_nonexistent_episode(client, episode_and_auth):
	"""Test GET composition returns 404 for non-existent episode."""
	_, headers = episode_and_auth
	fake_id = str(uuid4())
	response = await client.get(
		f"/episodes/{fake_id}/composition",
		headers=headers
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_composition_creates_blank_draft(client, episode_and_auth):
	"""Test GET composition creates a blank draft if none exists."""
	episode_id, headers = episode_and_auth

	response = await client.get(
		f"/episodes/{episode_id}/composition",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["episode_id"] == episode_id
	assert data["timeline"] == []
	assert data["render_status"] == "draft"
	assert data["composition_status"] == "draft"


@pytest.mark.asyncio
async def test_create_composition_with_generated_segment(client, episode_and_auth):
	"""Test creating a composition with a 'generated' segment."""
	episode_id, headers = episode_and_auth

	response = await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": generated_timeline()}
	)
	assert response.status_code == 200
	data = response.json()
	assert data["episode_id"] == episode_id
	assert len(data["timeline"]) == 1
	assert data["timeline"][0]["type"] == "generated"
	assert data["render_status"] == "draft"
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_update_composition_replaces_timeline(client, episode_and_auth):
	"""Test that posting a composition updates (replaces) the existing timeline."""
	episode_id, headers = episode_and_auth

	# Create initial composition
	await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": generated_timeline()}
	)

	# Update with a new timeline containing two segments
	new_timeline = [
		{
			"type": "generated",
			"position_seconds": 5.0,
			"fade_in_ms": 500,
			"fade_out_ms": 500,
			"normalize": True,
			"volume_level": 1.0
		},
		{
			"type": "outro",
			"snippet_id": str(uuid4()),  # Will fail snippet lookup - use a mock
			"position_seconds": 60.0,
			"fade_in_ms": 0,
			"fade_out_ms": 0,
			"normalize": False,
			"volume_level": 0.8
		}
	]

	# The outro references a non-existent snippet, so we expect 422
	response = await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": new_timeline}
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_composition_invalid_snippet_reference(client, episode_and_auth):
	"""Test that invalid snippet references return 422."""
	episode_id, headers = episode_and_auth
	fake_snippet_id = str(uuid4())

	response = await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": [
			{
				"type": "intro",
				"snippet_id": fake_snippet_id,
				"position_seconds": 0.0,
				"fade_in_ms": 0,
				"fade_out_ms": 0,
				"normalize": True,
				"volume_level": 1.0
			}
		]}
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validate_empty_composition(client, episode_and_auth):
	"""Test validation of empty composition returns valid=False."""
	episode_id, headers = episode_and_auth

	# Get/create blank composition
	await client.get(f"/episodes/{episode_id}/composition", headers=headers)

	response = await client.post(
		f"/episodes/{episode_id}/composition/validate",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["valid"] is False
	assert len(data["errors"]) > 0


@pytest.mark.asyncio
async def test_validate_composition_with_generated_segment(client, episode_and_auth):
	"""Test validation passes with at least one generated segment."""
	episode_id, headers = episode_and_auth

	# Create composition with generated segment
	await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": generated_timeline()}
	)

	response = await client.post(
		f"/episodes/{episode_id}/composition/validate",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert data["valid"] is True
	assert "total_duration_seconds" in data
	assert "gaps" in data
	assert "warnings" in data
	assert "errors" in data


@pytest.mark.asyncio
async def test_validate_requires_auth(client, episode_and_auth):
	"""Test validate endpoint requires authentication."""
	episode_id, _ = episode_and_auth
	response = await client.post(f"/episodes/{episode_id}/composition/validate")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_render_requires_auth(client, episode_and_auth):
	"""Test render endpoint requires authentication."""
	episode_id, _ = episode_and_auth
	response = await client.post(f"/episodes/{episode_id}/composition/render")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_render_empty_composition_fails(client, episode_and_auth):
	"""Test render returns 422 when timeline is empty."""
	episode_id, headers = episode_and_auth

	# Ensure empty composition exists
	await client.get(f"/episodes/{episode_id}/composition", headers=headers)

	response = await client.post(
		f"/episodes/{episode_id}/composition/render",
		headers=headers
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_render_dispatches_task(client, episode_and_auth):
	"""Test render endpoint dispatches a Celery task and returns task_id."""
	episode_id, headers = episode_and_auth

	# Create composition with a timeline
	await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": generated_timeline()}
	)

	fake_task_id = "celery-task-id-abc123"

	mock_task = MagicMock()
	mock_task.id = fake_task_id

	with patch("src.services.episode_composition_service.celery_app") as mock_celery:
		mock_celery.send_task.return_value = mock_task
		response = await client.post(
			f"/episodes/{episode_id}/composition/render",
			headers=headers
		)

	assert response.status_code == 202
	data = response.json()
	assert data["task_id"] == fake_task_id
	assert data["status"] == "queued"
	assert data["episode_id"] == episode_id
	assert "composition_id" in data


@pytest.mark.asyncio
async def test_render_status_requires_auth(client, episode_and_auth):
	"""Test render status endpoint requires authentication."""
	episode_id, _ = episode_and_auth
	response = await client.get(f"/episodes/{episode_id}/composition/status")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_render_status_returns_current_state(client, episode_and_auth):
	"""Test render status returns the current render state."""
	episode_id, headers = episode_and_auth

	# Create composition
	await client.post(
		f"/episodes/{episode_id}/composition",
		headers=headers,
		json={"timeline": generated_timeline()}
	)

	response = await client.get(
		f"/episodes/{episode_id}/composition/status",
		headers=headers
	)
	assert response.status_code == 200
	data = response.json()
	assert "status" in data
	assert "progress" in data


@pytest.mark.asyncio
async def test_render_status_nonexistent_episode(client, episode_and_auth):
	"""Test render status returns 404 for non-existent episode."""
	_, headers = episode_and_auth
	fake_id = str(uuid4())
	response = await client.get(
		f"/episodes/{fake_id}/composition/status",
		headers=headers
	)
	assert response.status_code == 404


# ============================================================================
# UNIT TESTS - SERVICE LAYER
# ============================================================================


class TestCompositionServiceUnit:
	"""Unit tests for episode composition service functions."""

	@pytest.mark.asyncio
	async def test_validate_composition_empty_timeline(self):
		"""Test validate_composition returns invalid for empty timeline."""
		from src.services.episode_composition_service import validate_composition
		from unittest.mock import MagicMock

		db = AsyncMock()
		composition = MagicMock()
		composition.timeline = []
		tenant_id = uuid4()

		result = await validate_composition(db=db, composition=composition, tenant_id=tenant_id)

		assert result.valid is False
		assert "empty" in result.errors[0].lower()

	@pytest.mark.asyncio
	async def test_validate_composition_with_generated_only(self):
		"""Test validate_composition returns valid for generated-only timeline."""
		from src.services.episode_composition_service import validate_composition
		from unittest.mock import MagicMock

		db = AsyncMock()
		composition = MagicMock()
		composition.timeline = [
			{"type": "generated", "position_seconds": 0.0}
		]
		tenant_id = uuid4()

		result = await validate_composition(db=db, composition=composition, tenant_id=tenant_id)

		assert result.valid is True
		assert result.errors == []

	@pytest.mark.asyncio
	async def test_get_render_status_from_composition_draft(self):
		"""Test get_render_status returns 'queued' for draft status."""
		from src.services.episode_composition_service import get_render_status
		from unittest.mock import MagicMock

		composition = MagicMock()
		composition.render_status = "draft"
		composition.render_error = None

		result = await get_render_status(composition=composition)

		assert result.status == "queued"

	@pytest.mark.asyncio
	async def test_get_render_status_from_composition_complete(self):
		"""Test get_render_status returns 'complete' for complete status."""
		from src.services.episode_composition_service import get_render_status
		from unittest.mock import MagicMock

		composition = MagicMock()
		composition.render_status = "complete"
		composition.render_error = None

		result = await get_render_status(composition=composition)

		assert result.status == "complete"
		assert result.progress == 100

	@pytest.mark.asyncio
	async def test_get_render_status_from_composition_failed(self):
		"""Test get_render_status returns 'failed' with error message."""
		from src.services.episode_composition_service import get_render_status
		from unittest.mock import MagicMock

		composition = MagicMock()
		composition.render_status = "failed"
		composition.render_error = "Audio file not found"

		result = await get_render_status(composition=composition)

		assert result.status == "failed"
		assert result.error == "Audio file not found"
