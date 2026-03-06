"""
Tests for TTS configuration CRUD API (GAP-075).

Tests create, read, update, delete operations, pagination,
default flag management, and ownership isolation.
"""

import pytest
from uuid import uuid4


@pytest.fixture
async def auth_headers(client):
    """Register a user and return auth headers."""
    reg_response = await client.post("/auth/register", json={
        "email": f"tts_test_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "TTS Test User"
    })
    assert reg_response.status_code == 201
    token = reg_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_auth_headers(client):
    """Register a second user and return auth headers."""
    reg_response = await client.post("/auth/register", json={
        "email": f"tts_other_{uuid4()}@example.com",
        "password": "SecurePass123!",
        "full_name": "Other TTS User"
    })
    assert reg_response.status_code == 201
    token = reg_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# CREATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_tts_config_openai(client, auth_headers):
    """Test creating an OpenAI TTS configuration."""
    response = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "My OpenAI Config",
        "provider": "openai",
        "config": {
            "model": "tts-1-hd",
            "voice_1": "alloy",
            "voice_2": "echo"
        },
        "is_default": False
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My OpenAI Config"
    assert data["provider"] == "openai"
    assert data["config"]["model"] == "tts-1-hd"
    assert data["is_default"] is False
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_tts_config_elevenlabs(client, auth_headers):
    """Test creating an ElevenLabs TTS configuration."""
    response = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "ElevenLabs Premium",
        "provider": "elevenlabs",
        "config": {
            "model": "eleven_multilingual_v2",
            "voice_1_id": "21m00Tcm4TlvDq8ikWAM"
        }
    })
    assert response.status_code == 201
    data = response.json()
    assert data["provider"] == "elevenlabs"
    assert data["config"]["model"] == "eleven_multilingual_v2"


@pytest.mark.asyncio
async def test_create_tts_config_edge(client, auth_headers):
    """Test creating an Edge TTS configuration."""
    response = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Edge Free",
        "provider": "edge",
        "config": {
            "voice_1": "en-US-AriaNeural",
            "voice_2": "en-US-GuyNeural"
        }
    })
    assert response.status_code == 201
    data = response.json()
    assert data["provider"] == "edge"


@pytest.mark.asyncio
async def test_create_tts_config_default_applies_defaults(client, auth_headers):
    """Test that provider defaults are applied to config when fields missing."""
    response = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Minimal OpenAI",
        "provider": "openai",
        "config": {}
    })
    assert response.status_code == 201
    data = response.json()
    # Default fields should be set by schema validator
    assert "model" in data["config"]
    assert "voice_1" in data["config"]


@pytest.mark.asyncio
async def test_create_tts_config_invalid_provider(client, auth_headers):
    """Test that invalid provider is rejected."""
    response = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Invalid Provider",
        "provider": "invalid_provider",
        "config": {}
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_tts_config_sets_default_clears_others(client, auth_headers):
    """Test that setting is_default=True clears other defaults."""
    # Create first config as default
    r1 = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Config 1",
        "provider": "openai",
        "config": {},
        "is_default": True
    })
    assert r1.status_code == 201
    config1_id = r1.json()["id"]

    # Create second config as default
    r2 = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Config 2",
        "provider": "edge",
        "config": {},
        "is_default": True
    })
    assert r2.status_code == 201
    config2_id = r2.json()["id"]

    # First config should no longer be default
    r_get1 = await client.get(f"/tts-configs/{config1_id}", headers=auth_headers)
    assert r_get1.json()["is_default"] is False

    # Second config should be default
    r_get2 = await client.get(f"/tts-configs/{config2_id}", headers=auth_headers)
    assert r_get2.json()["is_default"] is True


@pytest.mark.asyncio
async def test_create_tts_config_requires_auth(client):
    """Test that unauthenticated requests are rejected."""
    response = await client.post("/tts-configs", json={
        "name": "Test",
        "provider": "openai",
        "config": {}
    })
    assert response.status_code == 401


# ============================================================================
# READ TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_tts_configs_empty(client, auth_headers):
    """Test listing configs returns empty list when none created."""
    response = await client.get("/tts-configs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["tts_configs"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_tts_configs(client, auth_headers):
    """Test listing multiple configurations."""
    # Create 3 configs
    for i in range(3):
        await client.post("/tts-configs", headers=auth_headers, json={
            "name": f"Config {i}",
            "provider": "openai",
            "config": {}
        })

    response = await client.get("/tts-configs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["tts_configs"]) == 3
    assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_tts_configs_pagination(client, auth_headers):
    """Test pagination of TTS configs."""
    # Create 5 configs
    for i in range(5):
        await client.post("/tts-configs", headers=auth_headers, json={
            "name": f"Config {i}",
            "provider": "openai",
            "config": {}
        })

    # Get page 1 with page_size=2
    r1 = await client.get("/tts-configs?page=1&page_size=2", headers=auth_headers)
    assert r1.status_code == 200
    d1 = r1.json()
    assert len(d1["tts_configs"]) == 2
    assert d1["total"] == 5
    assert d1["total_pages"] == 3

    # Get page 3
    r3 = await client.get("/tts-configs?page=3&page_size=2", headers=auth_headers)
    assert r3.status_code == 200
    d3 = r3.json()
    assert len(d3["tts_configs"]) == 1


@pytest.mark.asyncio
async def test_get_tts_config_by_id(client, auth_headers):
    """Test getting a config by ID."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "My Config",
        "provider": "gemini",
        "config": {"language_code": "en-US"}
    })
    config_id = create_r.json()["id"]

    response = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == config_id
    assert data["provider"] == "gemini"


@pytest.mark.asyncio
async def test_get_tts_config_not_found(client, auth_headers):
    """Test 404 for nonexistent config."""
    response = await client.get(f"/tts-configs/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_tts_config_other_user_returns_404(client, auth_headers, other_auth_headers):
    """Test that another user's config returns 404 (ownership isolation)."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Private Config",
        "provider": "openai",
        "config": {}
    })
    config_id = create_r.json()["id"]

    # Other user cannot see it
    response = await client.get(f"/tts-configs/{config_id}", headers=other_auth_headers)
    assert response.status_code == 404


# ============================================================================
# UPDATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_tts_config_name(client, auth_headers):
    """Test updating the name of a config."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Old Name",
        "provider": "openai",
        "config": {}
    })
    config_id = create_r.json()["id"]

    update_r = await client.put(f"/tts-configs/{config_id}", headers=auth_headers, json={
        "name": "New Name"
    })
    assert update_r.status_code == 200
    assert update_r.json()["name"] == "New Name"
    # Provider unchanged
    assert update_r.json()["provider"] == "openai"


@pytest.mark.asyncio
async def test_update_tts_config_config_field(client, auth_headers):
    """Test updating config fields."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Config",
        "provider": "openai",
        "config": {"voice_1": "alloy"}
    })
    config_id = create_r.json()["id"]

    update_r = await client.put(f"/tts-configs/{config_id}", headers=auth_headers, json={
        "config": {"voice_1": "nova", "voice_2": "echo"}
    })
    assert update_r.status_code == 200
    assert update_r.json()["config"]["voice_1"] == "nova"


@pytest.mark.asyncio
async def test_update_tts_config_set_default(client, auth_headers):
    """Test setting a config as default via update."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "Config",
        "provider": "openai",
        "config": {},
        "is_default": False
    })
    config_id = create_r.json()["id"]

    update_r = await client.put(f"/tts-configs/{config_id}", headers=auth_headers, json={
        "is_default": True
    })
    assert update_r.status_code == 200
    assert update_r.json()["is_default"] is True


@pytest.mark.asyncio
async def test_update_tts_config_not_found(client, auth_headers):
    """Test 404 for updating nonexistent config."""
    response = await client.put(f"/tts-configs/{uuid4()}", headers=auth_headers, json={
        "name": "Whatever"
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_tts_config_other_user_returns_404(client, auth_headers, other_auth_headers):
    """Test that another user cannot update a config."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "My Config",
        "provider": "openai",
        "config": {}
    })
    config_id = create_r.json()["id"]

    response = await client.put(f"/tts-configs/{config_id}", headers=other_auth_headers, json={
        "name": "Hijacked"
    })
    assert response.status_code == 404


# ============================================================================
# DELETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_delete_tts_config(client, auth_headers):
    """Test deleting a TTS configuration."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "To Delete",
        "provider": "openai",
        "config": {}
    })
    config_id = create_r.json()["id"]

    delete_r = await client.delete(f"/tts-configs/{config_id}", headers=auth_headers)
    assert delete_r.status_code == 204

    # Verify it's gone
    get_r = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
    assert get_r.status_code == 404


@pytest.mark.asyncio
async def test_delete_tts_config_not_found(client, auth_headers):
    """Test 404 for deleting nonexistent config."""
    response = await client.delete(f"/tts-configs/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_tts_config_other_user_returns_404(client, auth_headers, other_auth_headers):
    """Test that another user cannot delete a config."""
    create_r = await client.post("/tts-configs", headers=auth_headers, json={
        "name": "My Config",
        "provider": "openai",
        "config": {}
    })
    config_id = create_r.json()["id"]

    response = await client.delete(f"/tts-configs/{config_id}", headers=other_auth_headers)
    assert response.status_code == 404

    # Original still exists
    get_r = await client.get(f"/tts-configs/{config_id}", headers=auth_headers)
    assert get_r.status_code == 200


# ============================================================================
# LIST ISOLATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_tts_configs_only_own(client, auth_headers, other_auth_headers):
    """Test that list only returns the current user's configs."""
    # User 1 creates 2 configs
    for i in range(2):
        await client.post("/tts-configs", headers=auth_headers, json={
            "name": f"User1 Config {i}",
            "provider": "openai",
            "config": {}
        })

    # User 2 creates 1 config
    await client.post("/tts-configs", headers=other_auth_headers, json={
        "name": "User2 Config",
        "provider": "edge",
        "config": {}
    })

    # Each user only sees their own
    r1 = await client.get("/tts-configs", headers=auth_headers)
    assert r1.json()["total"] == 2

    r2 = await client.get("/tts-configs", headers=other_auth_headers)
    assert r2.json()["total"] == 1
