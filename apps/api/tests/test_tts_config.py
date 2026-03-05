"""
Comprehensive test suite for TTS Configuration CRUD API.

Tests CRUD operations, pagination, validation, set-default functionality,
and authentication for TTS configuration endpoints.
"""

import pytest
from uuid import uuid4


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

OPENAI_CONFIG = {
	"model": "tts-1-hd",
	"voice_1": "alloy",
	"voice_2": "echo",
	"speed": 1.0,
}

ELEVENLABS_CONFIG = {
	"model": "eleven_multilingual_v2",
	"voice_1_id": "21m00Tcm4TlvDq8ikWAM",
	"voice_2_id": "AZnzlk1XvdvUeBnXmlld",
	"stability": 0.5,
	"similarity_boost": 0.75,
}

GEMINI_CONFIG = {
	"model": "en-US-Studio-MultiSpeaker",
	"language_code": "en-US",
}

EDGE_CONFIG = {
	"voice_1": "en-US-AriaNeural",
	"voice_2": "en-US-GuyNeural",
	"rate": "+0%",
	"volume": "+0%",
}


@pytest.fixture
async def auth_headers(client):
	"""Create user and return auth headers."""
	response = await client.post("/auth/register", json={
		"email": f"test_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "Test User"
	})
	assert response.status_code == 201
	token = response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


async def _create_config(client, headers, provider="openai", config=None, name=None, is_default=False):
	"""Helper to create a TTS configuration."""
	if config is None:
		config = OPENAI_CONFIG
	if name is None:
		name = f"Config {uuid4()}"
	response = await client.post("/tts-configs", headers=headers, json={
		"name": name,
		"provider": provider,
		"config": config,
		"is_default": is_default,
	})
	return response


# ============================================================================
# CRUD TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_tts_configuration_openai(client, auth_headers):
	"""Test successful OpenAI TTS configuration creation."""
	response = await _create_config(
		client, auth_headers, provider="openai", config=OPENAI_CONFIG, name="My OpenAI Config"
	)
	assert response.status_code == 201
	data = response.json()
	assert data["name"] == "My OpenAI Config"
	assert data["provider"] == "openai"
	assert data["config"] == OPENAI_CONFIG
	assert data["is_default"] is False
	assert "id" in data
	assert "user_id" in data
	assert "tenant_id" in data
	assert "created_at" in data
	assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_tts_configuration_elevenlabs(client, auth_headers):
	"""Test successful ElevenLabs TTS configuration creation."""
	response = await _create_config(
		client, auth_headers, provider="elevenlabs", config=ELEVENLABS_CONFIG, name="ElevenLabs Config"
	)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "elevenlabs"
	assert data["config"]["voice_1_id"] == ELEVENLABS_CONFIG["voice_1_id"]


@pytest.mark.asyncio
async def test_create_tts_configuration_gemini(client, auth_headers):
	"""Test successful Gemini TTS configuration creation."""
	response = await _create_config(
		client, auth_headers, provider="gemini", config=GEMINI_CONFIG, name="Gemini Config"
	)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "gemini"
	assert data["config"]["language_code"] == "en-US"


@pytest.mark.asyncio
async def test_create_tts_configuration_gemini_multi(client, auth_headers):
	"""Test successful Gemini Multi TTS configuration creation."""
	response = await _create_config(
		client, auth_headers, provider="gemini_multi", config=GEMINI_CONFIG, name="Gemini Multi Config"
	)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "gemini_multi"


@pytest.mark.asyncio
async def test_create_tts_configuration_edge(client, auth_headers):
	"""Test successful Edge TTS configuration creation."""
	response = await _create_config(
		client, auth_headers, provider="edge", config=EDGE_CONFIG, name="Edge Config"
	)
	assert response.status_code == 201
	data = response.json()
	assert data["provider"] == "edge"
	assert data["config"]["voice_1"] == "en-US-AriaNeural"


@pytest.mark.asyncio
async def test_create_tts_configuration_as_default(client, auth_headers):
	"""Test creating a TTS configuration with is_default=True."""
	response = await _create_config(
		client, auth_headers, is_default=True, name="Default Config"
	)
	assert response.status_code == 201
	assert response.json()["is_default"] is True


@pytest.mark.asyncio
async def test_list_tts_configurations_empty(client, auth_headers):
	"""Test listing configurations when none exist."""
	response = await client.get("/tts-configs", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert data["tts_configs"] == []
	assert data["page"] == 1
	assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_tts_configurations(client, auth_headers):
	"""Test listing configurations with multiple entries."""
	for i in range(3):
		await _create_config(client, auth_headers, name=f"Config {i}")

	response = await client.get("/tts-configs", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 3
	assert len(data["tts_configs"]) == 3
	assert data["page"] == 1
	assert data["page_size"] == 20
	assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_tts_configurations_pagination(client, auth_headers):
	"""Test pagination for TTS configurations."""
	for i in range(5):
		await _create_config(client, auth_headers, name=f"Config {i}")

	response = await client.get("/tts-configs?page=1&page_size=3", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 5
	assert len(data["tts_configs"]) == 3
	assert data["total_pages"] == 2

	response2 = await client.get("/tts-configs?page=2&page_size=3", headers=auth_headers)
	assert response2.status_code == 200
	data2 = response2.json()
	assert len(data2["tts_configs"]) == 2
	assert data2["page"] == 2


@pytest.mark.asyncio
async def test_get_tts_configuration_by_id(client, auth_headers):
	"""Test retrieving a specific TTS configuration by ID."""
	create_response = await _create_config(client, auth_headers, name="Specific Config")
	assert create_response.status_code == 201
	config_id = create_response.json()["id"]

	response = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["id"] == config_id
	assert data["name"] == "Specific Config"


@pytest.mark.asyncio
async def test_get_tts_configuration_not_found(client, auth_headers):
	"""Test 404 for nonexistent TTS configuration."""
	fake_id = str(uuid4())
	response = await client.get(f"/tts-configs/{fake_id}", headers=auth_headers)
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_tts_configuration_name(client, auth_headers):
	"""Test partial update of TTS configuration (name only)."""
	create_response = await _create_config(client, auth_headers, name="Original Name")
	config_id = create_response.json()["id"]

	response = await client.put(f"/tts-configs/{config_id}", headers=auth_headers, json={
		"name": "Updated Name"
	})
	assert response.status_code == 200
	data = response.json()
	assert data["name"] == "Updated Name"
	assert data["provider"] == "openai"  # Unchanged


@pytest.mark.asyncio
async def test_update_tts_configuration_config(client, auth_headers):
	"""Test updating the config dict of a TTS configuration."""
	create_response = await _create_config(client, auth_headers)
	config_id = create_response.json()["id"]

	new_config = {
		"model": "tts-1",
		"voice_1": "nova",
		"voice_2": "shimmer",
	}
	response = await client.put(f"/tts-configs/{config_id}", headers=auth_headers, json={
		"config": new_config
	})
	assert response.status_code == 200
	assert response.json()["config"]["voice_1"] == "nova"


@pytest.mark.asyncio
async def test_update_tts_configuration_not_found(client, auth_headers):
	"""Test 404 when updating nonexistent TTS configuration."""
	fake_id = str(uuid4())
	response = await client.put(f"/tts-configs/{fake_id}", headers=auth_headers, json={
		"name": "New Name"
	})
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_tts_configuration(client, auth_headers):
	"""Test hard delete of TTS configuration."""
	create_response = await _create_config(client, auth_headers, name="To Delete")
	config_id = create_response.json()["id"]

	response = await client.delete(f"/tts-configs/{config_id}", headers=auth_headers)
	assert response.status_code == 204

	# Verify it's gone
	get_response = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
	assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_tts_configuration_not_found(client, auth_headers):
	"""Test 404 when deleting nonexistent TTS configuration."""
	fake_id = str(uuid4())
	response = await client.delete(f"/tts-configs/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_default_tts_configuration(client, auth_headers):
	"""Test setting a TTS configuration as default."""
	create_response = await _create_config(client, auth_headers, name="My Config")
	config_id = create_response.json()["id"]

	response = await client.post(f"/tts-configs/{config_id}/set-default", headers=auth_headers)
	assert response.status_code == 200
	assert response.json()["is_default"] is True
	assert response.json()["id"] == config_id


@pytest.mark.asyncio
async def test_set_default_clears_previous_default(client, auth_headers):
	"""Test that setting a new default clears the previous one."""
	r1 = await _create_config(client, auth_headers, name="Config 1", is_default=True)
	config1_id = r1.json()["id"]

	r2 = await _create_config(client, auth_headers, name="Config 2")
	config2_id = r2.json()["id"]

	# Set config 2 as default
	response = await client.post(f"/tts-configs/{config2_id}/set-default", headers=auth_headers)
	assert response.status_code == 200
	assert response.json()["is_default"] is True

	# Config 1 should no longer be default
	get1 = await client.get(f"/tts-configs/{config1_id}", headers=auth_headers)
	assert get1.json()["is_default"] is False


@pytest.mark.asyncio
async def test_set_default_not_found(client, auth_headers):
	"""Test 404 when setting default on nonexistent configuration."""
	fake_id = str(uuid4())
	response = await client.post(f"/tts-configs/{fake_id}/set-default", headers=auth_headers)
	assert response.status_code == 404


# ============================================================================
# VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_invalid_provider(client, auth_headers):
	"""Test 422 for invalid provider type."""
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "invalid_provider",
		"config": OPENAI_CONFIG,
	})
	assert response.status_code == 422
	assert "invalid" in response.text.lower()


@pytest.mark.asyncio
async def test_create_openai_missing_required_field(client, auth_headers):
	"""Test 422 for OpenAI config missing required field."""
	bad_config = {"model": "tts-1-hd", "voice_1": "alloy"}  # missing voice_2
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "openai",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_openai_invalid_model(client, auth_headers):
	"""Test 422 for OpenAI config with invalid model."""
	bad_config = {"model": "invalid-model", "voice_1": "alloy", "voice_2": "echo"}
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "openai",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_openai_invalid_voice(client, auth_headers):
	"""Test 422 for OpenAI config with invalid voice."""
	bad_config = {"model": "tts-1-hd", "voice_1": "not-a-voice", "voice_2": "echo"}
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "openai",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_openai_invalid_speed(client, auth_headers):
	"""Test 422 for OpenAI config with speed out of range."""
	bad_config = {"model": "tts-1-hd", "voice_1": "alloy", "voice_2": "echo", "speed": 5.0}
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "openai",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_elevenlabs_missing_required_field(client, auth_headers):
	"""Test 422 for ElevenLabs config missing required field."""
	bad_config = {"model": "eleven_multilingual_v2", "voice_1_id": "abc"}  # missing voice_2_id
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "elevenlabs",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_elevenlabs_invalid_stability(client, auth_headers):
	"""Test 422 for ElevenLabs config with stability out of range."""
	bad_config = {
		"model": "eleven_multilingual_v2",
		"voice_1_id": "abc123",
		"voice_2_id": "def456",
		"stability": 1.5,
	}
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "elevenlabs",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_gemini_missing_required_field(client, auth_headers):
	"""Test 422 for Gemini config missing required field."""
	bad_config = {"model": "en-US-Studio-MultiSpeaker"}  # missing language_code
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "gemini",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_edge_missing_required_field(client, auth_headers):
	"""Test 422 for Edge TTS config missing required field."""
	bad_config = {"voice_1": "en-US-AriaNeural"}  # missing voice_2
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "edge",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_edge_invalid_rate_format(client, auth_headers):
	"""Test 422 for Edge TTS config with invalid rate format."""
	bad_config = {
		"voice_1": "en-US-AriaNeural",
		"voice_2": "en-US-GuyNeural",
		"rate": "invalid",
	}
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "Bad Config",
		"provider": "edge",
		"config": bad_config,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_empty_name(client, auth_headers):
	"""Test 422 for empty name."""
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "",
		"provider": "openai",
		"config": OPENAI_CONFIG,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_name_too_long(client, auth_headers):
	"""Test 422 for name exceeding max length."""
	response = await client.post("/tts-configs", headers=auth_headers, json={
		"name": "A" * 300,
		"provider": "openai",
		"config": OPENAI_CONFIG,
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_invalid_provider(client, auth_headers):
	"""Test 422 for invalid provider in update."""
	create_response = await _create_config(client, auth_headers)
	config_id = create_response.json()["id"]

	response = await client.put(f"/tts-configs/{config_id}", headers=auth_headers, json={
		"provider": "bad_provider"
	})
	assert response.status_code == 422


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_requires_auth(client):
	"""Test that creating TTS configuration requires authentication."""
	response = await client.post("/tts-configs", json={
		"name": "Config",
		"provider": "openai",
		"config": OPENAI_CONFIG,
	})
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_requires_auth(client):
	"""Test that listing TTS configurations requires authentication."""
	response = await client.get("/tts-configs")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_requires_auth(client):
	"""Test that getting a TTS configuration requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/tts-configs/{fake_id}")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_requires_auth(client):
	"""Test that updating a TTS configuration requires authentication."""
	fake_id = str(uuid4())
	response = await client.put(f"/tts-configs/{fake_id}", json={"name": "New Name"})
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_requires_auth(client):
	"""Test that deleting a TTS configuration requires authentication."""
	fake_id = str(uuid4())
	response = await client.delete(f"/tts-configs/{fake_id}")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_set_default_requires_auth(client):
	"""Test that set-default endpoint requires authentication."""
	fake_id = str(uuid4())
	response = await client.post(f"/tts-configs/{fake_id}/set-default")
	assert response.status_code == 403
