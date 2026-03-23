"""
Comprehensive test suite for TTS Configuration CRUD API.

Tests CRUD operations, pagination, validation, default configuration management,
and authentication for TTS configurations.
"""

import pytest
from uuid import uuid4


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

OPENAI_CONFIG = {
	"name": "OpenAI Setup",
	"provider": "openai",
	"config": {
		"model": "tts-1-hd",
		"voice_1": "alloy",
		"voice_2": "echo",
		"speed": 1.0,
	},
}

ELEVENLABS_CONFIG = {
	"name": "ElevenLabs Setup",
	"provider": "elevenlabs",
	"config": {
		"model": "eleven_multilingual_v2",
		"voice_1_id": "21m00Tcm4TlvDq8ikWAM",
		"voice_2_id": "AZnzlk1XvdvUeBnXmlld",
		"stability": 0.5,
		"similarity_boost": 0.75,
	},
}

GEMINI_CONFIG = {
	"name": "Gemini Setup",
	"provider": "gemini",
	"config": {
		"model": "en-US-Studio-MultiSpeaker",
		"language_code": "en-US",
	},
}

GEMINI_MULTI_CONFIG = {
	"name": "Gemini Multi Setup",
	"provider": "gemini_multi",
	"config": {
		"model": "en-US-Studio-MultiSpeaker",
		"language_code": "en-US",
	},
}

EDGE_CONFIG = {
	"name": "Edge TTS Setup",
	"provider": "edge",
	"config": {
		"voice_1": "en-US-AriaNeural",
		"voice_2": "en-US-GuyNeural",
		"rate": "+0%",
		"volume": "+0%",
	},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def auth_headers(client):
	"""Create user and return auth headers."""
	response = await client.post("/auth/register", json={
		"email": f"tts_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "TTS User",
	})
	assert response.status_code == 201
	token = response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


async def _create_config(client, auth_headers, payload=None):
	"""Helper to create a TTS config via API."""
	if payload is None:
		payload = OPENAI_CONFIG
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	return response


# ============================================================================
# CREATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_tts_config_openai(client, auth_headers):
	"""Test successful OpenAI TTS configuration creation."""
	response = await _create_config(client, auth_headers, OPENAI_CONFIG)
	assert response.status_code == 201
	data = response.json()
	assert data["name"] == "OpenAI Setup"
	assert data["provider"] == "openai"
	assert data["config"]["voice_1"] == "alloy"
	assert not data["is_default"]
	assert "id" in data
	assert "user_id" in data
	assert "tenant_id" in data
	assert "created_at" in data
	assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_tts_config_elevenlabs(client, auth_headers):
	"""Test successful ElevenLabs TTS configuration creation."""
	response = await _create_config(client, auth_headers, ELEVENLABS_CONFIG)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "elevenlabs"
	assert data["config"]["stability"] == 0.5


@pytest.mark.asyncio
async def test_create_tts_config_gemini(client, auth_headers):
	"""Test successful Gemini TTS configuration creation."""
	response = await _create_config(client, auth_headers, GEMINI_CONFIG)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "gemini"
	assert data["config"]["language_code"] == "en-US"


@pytest.mark.asyncio
async def test_create_tts_config_gemini_multi(client, auth_headers):
	"""Test successful Gemini Multi TTS configuration creation."""
	response = await _create_config(client, auth_headers, GEMINI_MULTI_CONFIG)
	assert response.status_code == 201
	assert response.json()["provider"] == "gemini_multi"


@pytest.mark.asyncio
async def test_create_tts_config_edge(client, auth_headers):
	"""Test successful Edge TTS configuration creation."""
	response = await _create_config(client, auth_headers, EDGE_CONFIG)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "edge"
	assert data["config"]["voice_1"] == "en-US-AriaNeural"


@pytest.mark.asyncio
async def test_create_tts_config_with_is_default(client, auth_headers):
	"""Test creating configuration with is_default=True."""
	payload = {**OPENAI_CONFIG, "is_default": True}
	response = await _create_config(client, auth_headers, payload)
	assert response.status_code == 201
	assert response.json()["is_default"]


# ============================================================================
# LIST TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_tts_configs_empty(client, auth_headers):
	"""Test listing when no configurations exist."""
	response = await client.get("/tts-configs", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert data["configs"] == []
	assert data["page"] == 1
	assert data["page_size"] == 20
	assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_tts_configs(client, auth_headers):
	"""Test listing configurations with pagination metadata."""
	await _create_config(client, auth_headers, OPENAI_CONFIG)
	await _create_config(client, auth_headers, GEMINI_CONFIG)

	response = await client.get("/tts-configs", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 2
	assert len(data["configs"]) == 2
	assert data["page"] == 1
	assert data["page_size"] == 20
	assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_tts_configs_pagination(client, auth_headers):
	"""Test pagination with multiple pages."""
	for i in range(25):
		payload = {**OPENAI_CONFIG, "name": f"Config {i}"}
		await _create_config(client, auth_headers, payload)

	page1 = await client.get("/tts-configs?page=1&page_size=20", headers=auth_headers)
	assert page1.status_code == 200
	d1 = page1.json()
	assert d1["total"] == 25
	assert len(d1["configs"]) == 20
	assert d1["total_pages"] == 2

	page2 = await client.get("/tts-configs?page=2&page_size=20", headers=auth_headers)
	assert page2.status_code == 200
	d2 = page2.json()
	assert len(d2["configs"]) == 5
	assert d2["page"] == 2


# ============================================================================
# GET BY ID TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_tts_config_by_id(client, auth_headers):
	"""Test retrieving specific configuration by ID."""
	create_resp = await _create_config(client, auth_headers, OPENAI_CONFIG)
	assert create_resp.status_code == 201
	config_id = create_resp.json()["id"]

	response = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["name"] == "OpenAI Setup"
	assert data["id"] == config_id


@pytest.mark.asyncio
async def test_get_nonexistent_tts_config(client, auth_headers):
	"""Test getting configuration that doesn't exist."""
	fake_id = str(uuid4())
	response = await client.get(f"/tts-configs/{fake_id}", headers=auth_headers)
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


# ============================================================================
# UPDATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_tts_config_name(client, auth_headers):
	"""Test partial update of configuration name only."""
	create_resp = await _create_config(client, auth_headers, OPENAI_CONFIG)
	config_id = create_resp.json()["id"]

	response = await client.put(
		f"/tts-configs/{config_id}",
		headers=auth_headers,
		json={"name": "Updated OpenAI"},
	)
	assert response.status_code == 200
	data = response.json()
	assert data["name"] == "Updated OpenAI"
	assert data["config"]["voice_1"] == "alloy"  # Unchanged


@pytest.mark.asyncio
async def test_update_tts_config_is_default(client, auth_headers):
	"""Test updating is_default flag."""
	create_resp = await _create_config(client, auth_headers, OPENAI_CONFIG)
	config_id = create_resp.json()["id"]

	response = await client.put(
		f"/tts-configs/{config_id}",
		headers=auth_headers,
		json={"is_default": True},
	)
	assert response.status_code == 200
	assert response.json()["is_default"]


@pytest.mark.asyncio
async def test_update_nonexistent_tts_config(client, auth_headers):
	"""Test updating configuration that doesn't exist."""
	fake_id = str(uuid4())
	response = await client.put(
		f"/tts-configs/{fake_id}",
		headers=auth_headers,
		json={"name": "New Name"},
	)
	assert response.status_code == 404


# ============================================================================
# DELETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_delete_tts_config(client, auth_headers):
	"""Test deleting a configuration."""
	create_resp = await _create_config(client, auth_headers, OPENAI_CONFIG)
	assert create_resp.status_code == 201
	config_id = create_resp.json()["id"]

	response = await client.delete(f"/tts-configs/{config_id}", headers=auth_headers)
	assert response.status_code == 204

	# Verify it's gone
	get_resp = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
	assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_tts_config(client, auth_headers):
	"""Test deleting configuration that doesn't exist."""
	fake_id = str(uuid4())
	response = await client.delete(f"/tts-configs/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_from_list(client, auth_headers):
	"""Test that deleted configuration no longer appears in list."""
	await _create_config(client, auth_headers, OPENAI_CONFIG)
	await _create_config(client, auth_headers, GEMINI_CONFIG)

	list_resp = await client.get("/tts-configs", headers=auth_headers)
	assert list_resp.json()["total"] == 2
	config_id = list_resp.json()["configs"][0]["id"]

	await client.delete(f"/tts-configs/{config_id}", headers=auth_headers)

	list_resp2 = await client.get("/tts-configs", headers=auth_headers)
	assert list_resp2.json()["total"] == 1


# ============================================================================
# SET DEFAULT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_set_default_tts_config(client, auth_headers):
	"""Test setting a configuration as default."""
	create_resp = await _create_config(client, auth_headers, OPENAI_CONFIG)
	config_id = create_resp.json()["id"]
	assert not create_resp.json()["is_default"]

	response = await client.post(
		f"/tts-configs/{config_id}/set-default",
		headers=auth_headers,
	)
	assert response.status_code == 200
	assert response.json()["is_default"]


@pytest.mark.asyncio
async def test_set_default_clears_previous_default(client, auth_headers):
	"""Test that setting a new default clears the previous one."""
	r1 = await _create_config(client, auth_headers, OPENAI_CONFIG)
	r2 = await _create_config(client, auth_headers, GEMINI_CONFIG)
	c1_id = r1.json()["id"]
	c2_id = r2.json()["id"]

	# Set config 1 as default
	await client.post(f"/tts-configs/{c1_id}/set-default", headers=auth_headers)

	# Set config 2 as default - should clear config 1
	response = await client.post(f"/tts-configs/{c2_id}/set-default", headers=auth_headers)
	assert response.status_code == 200
	assert response.json()["is_default"]

	# Config 1 should no longer be default
	c1_resp = await client.get(f"/tts-configs/{c1_id}", headers=auth_headers)
	assert not c1_resp.json()["is_default"]


@pytest.mark.asyncio
async def test_set_default_nonexistent_tts_config(client, auth_headers):
	"""Test set-default for nonexistent configuration returns 404."""
	fake_id = str(uuid4())
	response = await client.post(
		f"/tts-configs/{fake_id}/set-default",
		headers=auth_headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_with_is_default_true_clears_others(client, auth_headers):
	"""Test that creating with is_default=True clears existing defaults."""
	# Create first config and set as default
	r1 = await _create_config(client, auth_headers, OPENAI_CONFIG)
	c1_id = r1.json()["id"]
	await client.post(f"/tts-configs/{c1_id}/set-default", headers=auth_headers)

	# Create second config with is_default=True
	payload = {**GEMINI_CONFIG, "is_default": True}
	r2 = await _create_config(client, auth_headers, payload)
	assert r2.status_code == 201
	assert r2.json()["is_default"]

	# Config 1 should no longer be default
	c1_resp = await client.get(f"/tts-configs/{c1_id}", headers=auth_headers)
	assert not c1_resp.json()["is_default"]


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_tts_config_requires_auth(client):
	"""Test that creating configuration requires authentication."""
	response = await client.post("/tts-configs", json=OPENAI_CONFIG)
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_tts_configs_requires_auth(client):
	"""Test that listing configurations requires authentication."""
	response = await client.get("/tts-configs")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_tts_config_requires_auth(client):
	"""Test that getting configuration requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/tts-configs/{fake_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_tts_config_requires_auth(client):
	"""Test that updating configuration requires authentication."""
	fake_id = str(uuid4())
	response = await client.put(f"/tts-configs/{fake_id}", json={"name": "New"})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_tts_config_requires_auth(client):
	"""Test that deleting configuration requires authentication."""
	fake_id = str(uuid4())
	response = await client.delete(f"/tts-configs/{fake_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_set_default_tts_config_requires_auth(client):
	"""Test that set-default requires authentication."""
	fake_id = str(uuid4())
	response = await client.post(f"/tts-configs/{fake_id}/set-default")
	assert response.status_code == 401


# ============================================================================
# VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_validation_missing_name(client, auth_headers):
	"""Test validation when name is missing."""
	payload = {k: v for k, v in OPENAI_CONFIG.items() if k != "name"}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_empty_name(client, auth_headers):
	"""Test validation for empty name."""
	payload = {**OPENAI_CONFIG, "name": ""}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_name_too_long(client, auth_headers):
	"""Test validation for name exceeding 255 chars."""
	payload = {**OPENAI_CONFIG, "name": "A" * 300}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_invalid_provider(client, auth_headers):
	"""Test validation for invalid provider type."""
	payload = {**OPENAI_CONFIG, "provider": "unknown_provider"}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_missing_config(client, auth_headers):
	"""Test validation when config is missing."""
	payload = {k: v for k, v in OPENAI_CONFIG.items() if k != "config"}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_openai_missing_required_field(client, auth_headers):
	"""Test that OpenAI config missing required field is rejected."""
	payload = {
		**OPENAI_CONFIG,
		"config": {
			"model": "tts-1-hd",
			"voice_2": "echo",
			# missing voice_1
		},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_openai_speed_out_of_range(client, auth_headers):
	"""Test that OpenAI speed out of range is rejected."""
	payload = {
		**OPENAI_CONFIG,
		"config": {**OPENAI_CONFIG["config"], "speed": 5.0},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_elevenlabs_missing_required_field(client, auth_headers):
	"""Test that ElevenLabs config missing required field is rejected."""
	payload = {
		**ELEVENLABS_CONFIG,
		"config": {
			"model": "eleven_multilingual_v2",
			"voice_1_id": "21m00Tcm4TlvDq8ikWAM",
			# missing voice_2_id
		},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_elevenlabs_stability_out_of_range(client, auth_headers):
	"""Test that ElevenLabs stability out of range is rejected."""
	payload = {
		**ELEVENLABS_CONFIG,
		"config": {**ELEVENLABS_CONFIG["config"], "stability": 1.5},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_gemini_missing_required_field(client, auth_headers):
	"""Test that Gemini config missing required field is rejected."""
	payload = {
		**GEMINI_CONFIG,
		"config": {
			"model": "en-US-Studio-MultiSpeaker",
			# missing language_code
		},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_edge_missing_required_field(client, auth_headers):
	"""Test that Edge TTS config missing required field is rejected."""
	payload = {
		**EDGE_CONFIG,
		"config": {
			"voice_1": "en-US-AriaNeural",
			# missing voice_2
		},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_validation_extra_fields_accepted(client, auth_headers):
	"""Test that extra fields in config dict are accepted (forward-compatible)."""
	payload = {
		**OPENAI_CONFIG,
		"config": {**OPENAI_CONFIG["config"], "extra_future_field": "value"},
	}
	response = await client.post("/tts-configs", headers=auth_headers, json=payload)
	assert response.status_code == 201
