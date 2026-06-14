"""
Test suite for Distribution Target CRUD API endpoints.

Tests CRUD operations, OAuth flow, webhook management, pagination,
validation, and tenant isolation for distribution targets.
"""

import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock, MagicMock


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


# ============================================================================
# WEBHOOK CRUD TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_webhook_target(client, auth_headers):
	"""Test creating a webhook distribution target."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "n8n Automation",
		"url": "https://n8n.example.com/webhook/podcast-notifications",
		"method": "POST",
		"headers": {
			"Authorization": "Bearer secret-token",
			"Content-Type": "application/json"
		}
	})
	assert response.status_code == 201
	data = response.json()
	assert data["target_type"] == "webhook"
	assert data["is_active"] is True
	assert data["platform_name"] == "n8n Automation"
	assert "id" in data
	assert "user_id" in data
	assert "tenant_id" in data
	assert "created_at" in data
	assert "updated_at" in data
	# Credentials must NOT be in response
	assert "headers" not in data
	assert "url" not in data


@pytest.mark.asyncio
async def test_create_webhook_target_minimal(client, auth_headers):
	"""Test creating a webhook with minimal required fields."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Simple Webhook",
		"url": "https://hooks.example.com/notify",
		"method": "POST"
	})
	assert response.status_code == 201
	data = response.json()
	assert data["target_type"] == "webhook"
	assert data["platform_name"] == "Simple Webhook"
	assert data["project_id"] is None


@pytest.mark.asyncio
async def test_create_webhook_with_project_id(client, auth_headers):
	"""Test creating webhook target linked to a specific project."""
	# Create a project first
	project_response = await client.post("/projects", headers=auth_headers, json={
		"name": "Test Project",
		"podcast_metadata": {
			"show_title": "Show",
			"author": "Author",
			"description": "Desc"
		}
	})
	assert project_response.status_code == 201
	project_id = project_response.json()["id"]

	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Project Webhook",
		"url": "https://hooks.example.com/project",
		"method": "POST",
		"project_id": project_id
	})
	assert response.status_code == 201
	data = response.json()
	assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_create_webhook_sets_user_and_tenant(client, auth_headers):
	"""Test that webhook creation assigns user_id and tenant_id from auth token."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Test Webhook",
		"url": "https://hooks.example.com/test",
		"method": "POST"
	})
	assert response.status_code == 201
	data = response.json()
	assert data["user_id"] is not None
	assert data["tenant_id"] is not None


@pytest.mark.asyncio
async def test_create_webhook_get_method(client, auth_headers):
	"""Test creating webhook with GET method."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "GET Webhook",
		"url": "https://hooks.example.com/get-notify",
		"method": "GET"
	})
	assert response.status_code == 201


# ============================================================================
# WEBHOOK VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_webhook_url_must_be_https(client, auth_headers):
	"""Test that webhook URL must use HTTPS."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "HTTP Webhook",
		"url": "http://hooks.example.com/webhook",  # HTTP, not HTTPS
		"method": "POST"
	})
	assert response.status_code == 422
	assert "https" in response.text.lower() or "url" in response.text.lower()


@pytest.mark.asyncio
async def test_webhook_url_required(client, auth_headers):
	"""Test that webhook URL is required."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "No URL Webhook",
		"method": "POST"
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_name_required(client, auth_headers):
	"""Test that webhook name is required."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"url": "https://hooks.example.com/webhook",
		"method": "POST"
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_method_validation(client, auth_headers):
	"""Test that only POST and GET methods are allowed."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Invalid Method",
		"url": "https://hooks.example.com/webhook",
		"method": "DELETE"
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_url_max_length(client, auth_headers):
	"""Test that webhook URL cannot exceed 500 characters."""
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Long URL Webhook",
		"url": "https://hooks.example.com/" + "a" * 480,
		"method": "POST"
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_max_headers(client, auth_headers):
	"""Test that webhook cannot have more than 10 headers."""
	too_many_headers = {f"X-Header-{i}": f"value-{i}" for i in range(11)}
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Too Many Headers",
		"url": "https://hooks.example.com/webhook",
		"method": "POST",
		"headers": too_many_headers
	})
	assert response.status_code == 422


# ============================================================================
# APPLE PODCASTS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_apple_authorize_returns_instructions(client, auth_headers):
	"""Test that Apple Podcasts authorize returns setup instructions."""
	response = await client.post("/distribution-targets/apple/authorize", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert "message" in data
	assert "podcasts_connect_url" in data
	assert "setup_instructions" in data


@pytest.mark.asyncio
async def test_create_apple_target(client, auth_headers):
	"""Test creating an Apple Podcasts distribution target."""
	response = await client.post("/distribution-targets/apple", headers=auth_headers, json={
		"show_id": "12345678",
		"api_key": "sk-apple-api-key-here"
	})
	assert response.status_code == 201
	data = response.json()
	assert data["target_type"] == "apple_podcasts"
	assert data["is_active"] is True
	assert data["show_id"] == "12345678"
	# API key must NOT be in response
	assert "api_key" not in data
	assert "credentials" not in data


@pytest.mark.asyncio
async def test_apple_target_requires_show_id(client, auth_headers):
	"""Test that Apple Podcasts target requires show_id."""
	response = await client.post("/distribution-targets/apple", headers=auth_headers, json={
		"api_key": "sk-apple-key"
	})
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_apple_target_requires_api_key(client, auth_headers):
	"""Test that Apple Podcasts target requires api_key."""
	response = await client.post("/distribution-targets/apple", headers=auth_headers, json={
		"show_id": "12345678"
	})
	assert response.status_code == 422


# ============================================================================
# SPOTIFY OAUTH TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_spotify_authorize_returns_url_and_state(client, auth_headers):
	"""Test that Spotify authorize generates authorization URL with state."""
	with patch("src.routers.distribution_targets.settings") as mock_settings:
		mock_settings.SPOTIFY_CLIENT_ID = "test-client-id"
		mock_settings.SPOTIFY_REDIRECT_URI = "https://api.example.com/api/distribution-targets/spotify/callback"

		response = await client.post("/distribution-targets/spotify/authorize", headers=auth_headers)

	assert response.status_code == 200
	data = response.json()
	assert "authorize_url" in data
	assert "state" in data
	assert len(data["state"]) > 10  # State should be a meaningful token
	assert "accounts.spotify.com" in data["authorize_url"]


@pytest.mark.asyncio
async def test_spotify_authorize_requires_auth(client):
	"""Test that Spotify authorize requires authentication."""
	response = await client.post("/distribution-targets/spotify/authorize")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_spotify_authorize_missing_client_id(client, auth_headers):
	"""Test error when Spotify client ID not configured."""
	with patch("src.routers.distribution_targets.settings") as mock_settings:
		mock_settings.SPOTIFY_CLIENT_ID = None
		mock_settings.SPOTIFY_REDIRECT_URI = "https://api.example.com/callback"

		response = await client.post("/distribution-targets/spotify/authorize", headers=auth_headers)

	assert response.status_code == 503


@pytest.mark.asyncio
async def test_spotify_callback_creates_target(client, auth_headers):
	"""Test that Spotify OAuth callback creates distribution target."""
	# First get a valid state
	with patch("src.routers.distribution_targets.settings") as mock_settings:
		mock_settings.SPOTIFY_CLIENT_ID = "test-client-id"
		mock_settings.SPOTIFY_REDIRECT_URI = "https://api.example.com/callback"

		auth_response = await client.post(
			"/distribution-targets/spotify/authorize",
			headers=auth_headers
		)
	assert auth_response.status_code == 200
	state = auth_response.json()["state"]

	# Mock Spotify token exchange
	mock_token_response = {
		"access_token": "spotify-access-token",
		"refresh_token": "spotify-refresh-token",
		"expires_in": 3600,
		"token_type": "Bearer"
	}
	mock_show_response = {
		"id": "show-id-123",
		"name": "My Podcast Show"
	}

	with patch("src.services.distribution_target_service.httpx") as mock_httpx:
		mock_client = AsyncMock()
		mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
		mock_httpx.AsyncClient.return_value.__aexit__.return_value = None

		# Mock token exchange call
		token_resp = MagicMock()
		token_resp.status_code = 200
		token_resp.json.return_value = mock_token_response
		token_resp.raise_for_status = MagicMock()

		# Mock show info call
		show_resp = MagicMock()
		show_resp.status_code = 200
		show_resp.json.return_value = mock_show_response
		show_resp.raise_for_status = MagicMock()

		mock_client.post.return_value = token_resp
		mock_client.get.return_value = show_resp

		with patch("src.routers.distribution_targets.settings") as mock_settings:
			mock_settings.SPOTIFY_CLIENT_ID = "test-client-id"
			mock_settings.SPOTIFY_CLIENT_SECRET = "test-client-secret"
			mock_settings.SPOTIFY_REDIRECT_URI = "https://api.example.com/callback"

			response = await client.get(
				f"/distribution-targets/spotify/callback?code=auth-code-123&state={state}"
			)

	# Callback should redirect or return the created target info
	assert response.status_code in (200, 302)


@pytest.mark.asyncio
async def test_spotify_callback_invalid_state(client, auth_headers):
	"""Test that Spotify callback with invalid state returns 400."""
	response = await client.get(
		"/distribution-targets/spotify/callback?code=some-code&state=invalid-state-token"
	)
	assert response.status_code == 400


@pytest.mark.asyncio
async def test_spotify_callback_missing_code(client):
	"""Test that Spotify callback without code returns 422."""
	response = await client.get(
		"/distribution-targets/spotify/callback?state=some-state"
	)
	assert response.status_code == 422


# ============================================================================
# LIST DISTRIBUTION TARGETS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_distribution_targets_empty(client, auth_headers):
	"""Test listing when no targets exist."""
	response = await client.get("/distribution-targets", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 0
	assert len(data["targets"]) == 0
	assert data["page"] == 1
	assert data["page_size"] == 20
	assert data["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_distribution_targets_with_webhooks(client, auth_headers):
	"""Test listing distribution targets with created webhooks."""
	# Create 2 webhooks
	for i in range(2):
		await client.post("/distribution-targets/webhook", headers=auth_headers, json={
			"name": f"Webhook {i}",
			"url": f"https://hooks.example.com/webhook-{i}",
			"method": "POST"
		})

	response = await client.get("/distribution-targets", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 2
	assert len(data["targets"]) == 2
	assert data["total_pages"] == 1


@pytest.mark.asyncio
async def test_list_distribution_targets_pagination(client, auth_headers):
	"""Test pagination for distribution targets."""
	# Create 25 webhooks
	for i in range(25):
		await client.post("/distribution-targets/webhook", headers=auth_headers, json={
			"name": f"Webhook {i}",
			"url": f"https://hooks.example.com/webhook-{i}",
			"method": "POST"
		})

	# Page 1
	response = await client.get("/distribution-targets?page=1&page_size=10", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 25
	assert len(data["targets"]) == 10
	assert data["page"] == 1
	assert data["total_pages"] == 3

	# Page 3
	response = await client.get("/distribution-targets?page=3&page_size=10", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert len(data["targets"]) == 5


@pytest.mark.asyncio
async def test_list_distribution_targets_filter_by_type(client, auth_headers):
	"""Test filtering distribution targets by type."""
	# Create webhook
	await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "My Webhook",
		"url": "https://hooks.example.com/webhook",
		"method": "POST"
	})

	# Create Apple target
	await client.post("/distribution-targets/apple", headers=auth_headers, json={
		"show_id": "apple-show-123",
		"api_key": "apple-api-key-xyz"
	})

	# Filter by webhook type
	response = await client.get("/distribution-targets?target_type=webhook", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["targets"][0]["target_type"] == "webhook"

	# Filter by apple_podcasts type
	response = await client.get("/distribution-targets?target_type=apple_podcasts", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["targets"][0]["target_type"] == "apple_podcasts"


@pytest.mark.asyncio
async def test_list_distribution_targets_filter_by_project(client, auth_headers):
	"""Test filtering distribution targets by project_id."""
	# Create project
	project_response = await client.post("/projects", headers=auth_headers, json={
		"name": "Test Project",
		"podcast_metadata": {
			"show_title": "Show",
			"author": "Author",
			"description": "Desc"
		}
	})
	project_id = project_response.json()["id"]

	# Create one webhook linked to project, one without project
	await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Project Webhook",
		"url": "https://hooks.example.com/project",
		"method": "POST",
		"project_id": project_id
	})
	await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Global Webhook",
		"url": "https://hooks.example.com/global",
		"method": "POST"
	})

	# Filter by project
	response = await client.get(f"/distribution-targets?project_id={project_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["total"] == 1
	assert data["targets"][0]["platform_name"] == "Project Webhook"


# ============================================================================
# GET BY ID TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_distribution_target_by_id(client, auth_headers):
	"""Test retrieving a distribution target by ID."""
	# Create webhook
	create_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Test Webhook",
		"url": "https://hooks.example.com/test",
		"method": "POST"
	})
	assert create_response.status_code == 201
	target_id = create_response.json()["id"]

	# Get by ID
	response = await client.get(f"/distribution-targets/{target_id}", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert data["id"] == target_id
	assert data["target_type"] == "webhook"


@pytest.mark.asyncio
async def test_get_distribution_target_not_found(client, auth_headers):
	"""Test 404 for nonexistent target."""
	fake_id = str(uuid4())
	response = await client.get(f"/distribution-targets/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_distribution_target_never_returns_credentials(client, auth_headers):
	"""Test that target details never expose encrypted credentials."""
	# Create Apple target with API key
	create_response = await client.post("/distribution-targets/apple", headers=auth_headers, json={
		"show_id": "apple-show-123",
		"api_key": "super-secret-api-key"
	})
	assert create_response.status_code == 201
	target_id = create_response.json()["id"]

	# Get by ID - should not return credentials
	response = await client.get(f"/distribution-targets/{target_id}", headers=auth_headers)
	assert response.status_code == 200
	response_text = response.text
	assert "super-secret-api-key" not in response_text
	assert "api_key" not in response_text


# ============================================================================
# UPDATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_distribution_target_is_active(client, auth_headers):
	"""Test updating is_active status."""
	# Create webhook
	create_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Active Webhook",
		"url": "https://hooks.example.com/active",
		"method": "POST"
	})
	assert create_response.status_code == 201
	target_id = create_response.json()["id"]

	# Deactivate it
	response = await client.put(f"/distribution-targets/{target_id}", headers=auth_headers, json={
		"is_active": False
	})
	assert response.status_code == 200
	assert response.json()["is_active"] is False

	# Reactivate it
	response = await client.put(f"/distribution-targets/{target_id}", headers=auth_headers, json={
		"is_active": True
	})
	assert response.status_code == 200
	assert response.json()["is_active"] is True


@pytest.mark.asyncio
async def test_update_distribution_target_not_found(client, auth_headers):
	"""Test 404 when updating nonexistent target."""
	fake_id = str(uuid4())
	response = await client.put(f"/distribution-targets/{fake_id}", headers=auth_headers, json={
		"is_active": False
	})
	assert response.status_code == 404


# ============================================================================
# DELETE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_delete_distribution_target(client, auth_headers):
	"""Test deleting a distribution target."""
	# Create webhook
	create_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "To Delete",
		"url": "https://hooks.example.com/delete",
		"method": "POST"
	})
	assert create_response.status_code == 201
	target_id = create_response.json()["id"]

	# Delete it
	response = await client.delete(f"/distribution-targets/{target_id}", headers=auth_headers)
	assert response.status_code == 204

	# Verify gone
	get_response = await client.get(f"/distribution-targets/{target_id}", headers=auth_headers)
	assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_distribution_target_not_found(client, auth_headers):
	"""Test 404 when deleting nonexistent target."""
	fake_id = str(uuid4())
	response = await client.delete(f"/distribution-targets/{fake_id}", headers=auth_headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_from_list(client, auth_headers):
	"""Test that deleted target no longer appears in list."""
	# Create two webhooks
	await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Keep",
		"url": "https://hooks.example.com/keep",
		"method": "POST"
	})
	delete_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Delete Me",
		"url": "https://hooks.example.com/delete-me",
		"method": "POST"
	})
	target_id = delete_response.json()["id"]

	# Delete one
	await client.delete(f"/distribution-targets/{target_id}", headers=auth_headers)

	# List should only show one
	list_response = await client.get("/distribution-targets", headers=auth_headers)
	assert list_response.json()["total"] == 1


# ============================================================================
# TEST CONNECTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_test_connection_webhook(client, auth_headers):
	"""Test webhook connection test."""
	# Create webhook
	create_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Test Webhook",
		"url": "https://hooks.example.com/test",
		"method": "POST"
	})
	assert create_response.status_code == 201
	target_id = create_response.json()["id"]

	# Mock httpx for the test connection call
	with patch("src.services.distribution_target_service.httpx") as mock_httpx:
		mock_client = AsyncMock()
		mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
		mock_httpx.AsyncClient.return_value.__aexit__.return_value = None

		test_resp = MagicMock()
		test_resp.status_code = 200
		test_resp.raise_for_status = MagicMock()
		mock_client.post.return_value = test_resp

		response = await client.post(
			f"/distribution-targets/{target_id}/test",
			headers=auth_headers
		)

	assert response.status_code == 200
	data = response.json()
	assert "success" in data
	assert "platform" in data
	assert "message" in data


@pytest.mark.asyncio
async def test_test_connection_not_found(client, auth_headers):
	"""Test 404 when testing nonexistent target."""
	fake_id = str(uuid4())
	response = await client.post(f"/distribution-targets/{fake_id}/test", headers=auth_headers)
	assert response.status_code == 404


# ============================================================================
# TOKEN REFRESH TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_refresh_token_not_found(client, auth_headers):
	"""Test 404 when refreshing token for nonexistent target."""
	fake_id = str(uuid4())
	response = await client.post(
		f"/distribution-targets/{fake_id}/refresh-token",
		headers=auth_headers
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_refresh_token_on_non_spotify_returns_400(client, auth_headers):
	"""Test that token refresh only works for Spotify targets."""
	# Create webhook
	create_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Not Spotify",
		"url": "https://hooks.example.com/test",
		"method": "POST"
	})
	target_id = create_response.json()["id"]

	response = await client.post(
		f"/distribution-targets/{target_id}/refresh-token",
		headers=auth_headers
	)
	assert response.status_code == 400


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_webhook_requires_auth(client):
	"""Test that creating webhook requires authentication."""
	response = await client.post("/distribution-targets/webhook", json={
		"name": "Test",
		"url": "https://hooks.example.com/test",
		"method": "POST"
	})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_targets_requires_auth(client):
	"""Test that listing targets requires authentication."""
	response = await client.get("/distribution-targets")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_target_requires_auth(client):
	"""Test that getting target requires authentication."""
	fake_id = str(uuid4())
	response = await client.get(f"/distribution-targets/{fake_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_target_requires_auth(client):
	"""Test that updating target requires authentication."""
	fake_id = str(uuid4())
	response = await client.put(f"/distribution-targets/{fake_id}", json={"is_active": False})
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_target_requires_auth(client):
	"""Test that deleting target requires authentication."""
	fake_id = str(uuid4())
	response = await client.delete(f"/distribution-targets/{fake_id}")
	assert response.status_code == 401


@pytest.mark.asyncio
async def test_test_connection_requires_auth(client):
	"""Test that test connection requires authentication."""
	fake_id = str(uuid4())
	response = await client.post(f"/distribution-targets/{fake_id}/test")
	assert response.status_code == 401


# ============================================================================
# SCHEMA UNIT TESTS (no DB required)
# ============================================================================

def test_webhook_create_valid():
	"""Test valid webhook creation schema."""
	from src.schemas.distribution_target import WebhookDistributionCreate
	schema = WebhookDistributionCreate(
		name="Test Webhook",
		url="https://hooks.example.com/test",
		method="POST"
	)
	assert schema.name == "Test Webhook"
	assert str(schema.url) == "https://hooks.example.com/test"
	assert schema.method == "POST"


def test_webhook_create_http_rejected():
	"""Test that HTTP URL is rejected."""
	from src.schemas.distribution_target import WebhookDistributionCreate
	import pydantic
	with pytest.raises(pydantic.ValidationError) as exc_info:
		WebhookDistributionCreate(
			name="Test",
			url="http://hooks.example.com/test",
			method="POST"
		)
	assert "https" in str(exc_info.value).lower() or "url" in str(exc_info.value).lower()


@pytest.mark.parametrize("url", [
	"https://169.254.169.254/",
	"https://127.0.0.1/",
	"https://10.0.0.1/hook",
	"https://172.16.0.1/hook",
	"https://192.168.1.1/hook",
	"https://[::1]/",
	"https://localhost/hook",
])
def test_webhook_create_internal_url_rejected(url):
	"""SSRF: webhook URLs pointing at internal addresses are rejected (issue #206)."""
	from src.schemas.distribution_target import WebhookDistributionCreate
	import pydantic
	with pytest.raises(pydantic.ValidationError) as exc_info:
		WebhookDistributionCreate(name="Test", url=url, method="POST")
	assert "not allowed" in str(exc_info.value).lower()


def test_webhook_create_non_standard_port_rejected():
	"""SSRF: non-standard ports are rejected for webhook URLs (issue #206)."""
	from src.schemas.distribution_target import WebhookDistributionCreate
	import pydantic
	with pytest.raises(pydantic.ValidationError):
		WebhookDistributionCreate(
			name="Test", url="https://93.184.216.34:8443/hook", method="POST"
		)


def test_webhook_create_invalid_method():
	"""Test that invalid HTTP method is rejected."""
	from src.schemas.distribution_target import WebhookDistributionCreate
	import pydantic
	with pytest.raises(pydantic.ValidationError):
		WebhookDistributionCreate(
			name="Test",
			url="https://hooks.example.com/test",
			method="PATCH"
		)


def test_webhook_create_too_many_headers():
	"""Test that more than 10 headers is rejected."""
	from src.schemas.distribution_target import WebhookDistributionCreate
	import pydantic
	too_many = {f"X-Header-{i}": f"value-{i}" for i in range(11)}
	with pytest.raises(pydantic.ValidationError):
		WebhookDistributionCreate(
			name="Test",
			url="https://hooks.example.com/test",
			method="POST",
			headers=too_many
		)


def test_apple_create_valid():
	"""Test valid Apple Podcasts creation schema."""
	from src.schemas.distribution_target import AppleDistributionCreate
	schema = AppleDistributionCreate(
		show_id="12345678",
		api_key="apple-api-key"
	)
	assert schema.show_id == "12345678"
	assert schema.api_key == "apple-api-key"


def test_distribution_target_update_partial():
	"""Test partial update schema."""
	from src.schemas.distribution_target import DistributionTargetUpdate
	schema = DistributionTargetUpdate(is_active=False)
	assert schema.is_active is False


def test_distribution_target_update_empty():
	"""Test that empty update is valid."""
	from src.schemas.distribution_target import DistributionTargetUpdate
	schema = DistributionTargetUpdate()
	assert schema.is_active is None


# ============================================================================
# WEBHOOK HEADER ENCRYPTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_webhook_sensitive_headers_not_in_db_plaintext(client, auth_headers, test_db):
	"""Test that sensitive header values are encrypted before storage in DB."""
	from sqlalchemy import select
	from src.models.distribution_target import DistributionTarget

	plaintext_token = "super-secret-bearer-token-12345"
	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Encrypted Headers Webhook",
		"url": "https://hooks.example.com/encrypted",
		"method": "POST",
		"headers": {
			"Authorization": f"Bearer {plaintext_token}",
			"X-API-Key": "my-api-key-value"
		}
	})
	assert response.status_code == 201
	target_id = response.json()["id"]

	# Query DB directly to check stored config
	result = await test_db.execute(
		select(DistributionTarget).where(DistributionTarget.id == target_id)
	)
	target = result.scalar_one()
	stored_headers = target.config.get("headers", {})

	# Sensitive header values must NOT be stored as plaintext
	assert stored_headers.get("Authorization") != f"Bearer {plaintext_token}", \
		"Authorization header was stored in plaintext"
	assert stored_headers.get("X-API-Key") != "my-api-key-value", \
		"X-API-Key header was stored in plaintext"


@pytest.mark.asyncio
async def test_webhook_nonsensitive_headers_stored_plaintext(client, auth_headers, test_db):
	"""Test that non-sensitive header values are stored as-is."""
	from sqlalchemy import select
	from src.models.distribution_target import DistributionTarget

	response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Plaintext Headers Webhook",
		"url": "https://hooks.example.com/plain",
		"method": "POST",
		"headers": {
			"Content-Type": "application/json",
			"Accept": "application/json"
		}
	})
	assert response.status_code == 201
	target_id = response.json()["id"]

	# Query DB directly to check stored config
	result = await test_db.execute(
		select(DistributionTarget).where(DistributionTarget.id == target_id)
	)
	target = result.scalar_one()
	stored_headers = target.config.get("headers", {})

	# Non-sensitive headers should remain plaintext
	assert stored_headers.get("Content-Type") == "application/json"
	assert stored_headers.get("Accept") == "application/json"


@pytest.mark.asyncio
async def test_webhook_connection_test_with_encrypted_headers(client, auth_headers):
	"""Test that test_connection decrypts headers before sending the test request."""
	# Create webhook with sensitive header
	create_response = await client.post("/distribution-targets/webhook", headers=auth_headers, json={
		"name": "Decrypt Test Webhook",
		"url": "https://hooks.example.com/decrypt-test",
		"method": "POST",
		"headers": {
			"Authorization": "Bearer my-secret-token",
			"Content-Type": "application/json"
		}
	})
	assert create_response.status_code == 201
	target_id = create_response.json()["id"]

	# Mock httpx for the test connection call and capture what headers are sent
	with patch("src.services.distribution_target_service.httpx") as mock_httpx:
		mock_client = AsyncMock()
		mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
		mock_httpx.AsyncClient.return_value.__aexit__.return_value = None
		mock_httpx.HTTPStatusError = Exception

		test_resp = MagicMock()
		test_resp.status_code = 200
		test_resp.raise_for_status = MagicMock()
		mock_client.post.return_value = test_resp

		response = await client.post(
			f"/distribution-targets/{target_id}/test",
			headers=auth_headers
		)

	assert response.status_code == 200
	data = response.json()
	assert data["success"] is True

	# Verify the headers passed to httpx.post contain decrypted values
	call_args = mock_client.post.call_args
	sent_headers = call_args.kwargs.get("headers", {}) if call_args.kwargs else call_args[1].get("headers", {})
	assert sent_headers.get("Authorization") == "Bearer my-secret-token", \
		"Authorization header was not decrypted before sending test request"
	assert sent_headers.get("Content-Type") == "application/json", \
		"Content-Type header should remain as-is"


# ============================================================================
# WEBHOOK DISPATCH SSRF TESTS (issue #206)
# ============================================================================

@pytest.mark.parametrize("url", [
	"https://169.254.169.254/latest/meta-data/",
	"https://127.0.0.1/",
	"https://10.0.0.1/hook",
	"https://192.168.1.1/hook",
])
def test_distribute_via_webhook_blocks_internal(url):
	"""SSRF: dispatch-time guard rejects internal webhook targets (issue #206)."""
	from src.tasks.platform_distribution import _distribute_via_webhook

	task = MagicMock()
	config = {"url": url, "method": "POST"}

	with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
		with pytest.raises(ValueError) as exc_info:
			_distribute_via_webhook("ep-1", config, {"title": "x"}, task)
		assert "not allowed" in str(exc_info.value).lower()
		mock_post.assert_not_called()
		mock_get.assert_not_called()


def test_distribute_via_webhook_disables_redirects_for_public():
	"""Public webhook dispatch must disable redirects to prevent SSRF bounce."""
	from src.tasks.platform_distribution import _distribute_via_webhook

	task = MagicMock()
	config = {"url": "https://93.184.216.34/hook", "method": "POST"}
	resp = MagicMock()
	resp.raise_for_status = MagicMock()

	with patch("requests.post", return_value=resp) as mock_post:
		result = _distribute_via_webhook("ep-1", config, {"title": "x"}, task)

	assert result["status"] == "success"
	assert mock_post.call_args.kwargs.get("allow_redirects") is False
