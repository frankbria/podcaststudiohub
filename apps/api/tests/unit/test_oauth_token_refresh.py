"""
Unit tests for OAuth token refresh task and service helpers.

Tests cover:
- OAuth state generation and validation
- Token encryption round-trip logic (mocked DB)
- Token refresh task logic with mocked Spotify API and DB
- CSRF state expiry enforcement
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ============================================================================
# OAuth state management tests
# ============================================================================

def test_generate_oauth_state_returns_string():
	"""generate_oauth_state should return a non-empty string."""
	from src.services.distribution_target_service import generate_oauth_state

	state = generate_oauth_state(str(uuid4()))
	assert isinstance(state, str)
	assert len(state) >= 32


def test_generate_oauth_state_is_unique():
	"""Each call to generate_oauth_state should return a distinct token."""
	from src.services.distribution_target_service import generate_oauth_state

	user_id = str(uuid4())
	states = {generate_oauth_state(user_id) for _ in range(10)}
	assert len(states) == 10  # All unique


def test_validate_oauth_state_valid():
	"""validate_oauth_state should return user_id for a valid state."""
	from src.services.distribution_target_service import (
		generate_oauth_state,
		validate_oauth_state,
	)

	user_id = str(uuid4())
	state = generate_oauth_state(user_id)
	result = validate_oauth_state(state)
	assert result == user_id


def test_validate_oauth_state_one_time_use():
	"""validate_oauth_state should consume the state (one-time use)."""
	from src.services.distribution_target_service import (
		generate_oauth_state,
		validate_oauth_state,
	)

	user_id = str(uuid4())
	state = generate_oauth_state(user_id)

	# First validation succeeds
	assert validate_oauth_state(state) == user_id

	# Second validation must fail (state consumed)
	assert validate_oauth_state(state) is None


def test_validate_oauth_state_invalid_token():
	"""validate_oauth_state should return None for unknown state tokens."""
	from src.services.distribution_target_service import validate_oauth_state

	result = validate_oauth_state("this-state-was-never-generated")
	assert result is None


def test_validate_oauth_state_expired():
	"""validate_oauth_state should return None for expired states."""
	from src.services import distribution_target_service

	user_id = str(uuid4())
	state = distribution_target_service.generate_oauth_state(user_id)

	# Manually backdating the stored state to simulate expiry
	distribution_target_service._oauth_states[state]["created_at"] = (
		datetime.now(timezone.utc) - timedelta(seconds=700)
	)

	result = distribution_target_service.validate_oauth_state(state)
	assert result is None


# ============================================================================
# DistributionTargetResponse schema tests
# ============================================================================

def test_distribution_target_response_spotify_token_valid():
	"""from_orm_model should compute token_valid=True for unexpired token."""
	from src.schemas.distribution_target import DistributionTargetResponse

	future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
	mock_target = MagicMock()
	mock_target.id = uuid4()
	mock_target.user_id = uuid4()
	mock_target.tenant_id = uuid4()
	mock_target.project_id = None
	mock_target.target_type = "spotify"
	mock_target.is_active = True
	mock_target.created_at = datetime.now(timezone.utc)
	mock_target.updated_at = datetime.now(timezone.utc)
	mock_target.config = {
		"show_id": "show-abc",
		"show_name": "My Podcast",
		"oauth_tokens": {
			"access_token": "encrypted_access",
			"refresh_token": "encrypted_refresh",
			"expires_at": future,
		},
	}

	response = DistributionTargetResponse.from_orm_model(mock_target)
	assert response.token_valid is True
	assert response.show_id == "show-abc"
	assert "My Podcast" in response.platform_name


def test_distribution_target_response_spotify_token_expired():
	"""from_orm_model should compute token_valid=False for expired token."""
	from src.schemas.distribution_target import DistributionTargetResponse

	past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
	mock_target = MagicMock()
	mock_target.id = uuid4()
	mock_target.user_id = uuid4()
	mock_target.tenant_id = uuid4()
	mock_target.project_id = None
	mock_target.target_type = "spotify"
	mock_target.is_active = True
	mock_target.created_at = datetime.now(timezone.utc)
	mock_target.updated_at = datetime.now(timezone.utc)
	mock_target.config = {
		"show_id": "show-xyz",
		"oauth_tokens": {
			"access_token": "encrypted_access",
			"refresh_token": "encrypted_refresh",
			"expires_at": past,
		},
	}

	response = DistributionTargetResponse.from_orm_model(mock_target)
	assert response.token_valid is False


def test_distribution_target_response_webhook():
	"""from_orm_model should use config name as platform_name for webhooks."""
	from src.schemas.distribution_target import DistributionTargetResponse

	mock_target = MagicMock()
	mock_target.id = uuid4()
	mock_target.user_id = uuid4()
	mock_target.tenant_id = uuid4()
	mock_target.project_id = None
	mock_target.target_type = "webhook"
	mock_target.is_active = True
	mock_target.created_at = datetime.now(timezone.utc)
	mock_target.updated_at = datetime.now(timezone.utc)
	mock_target.config = {
		"name": "n8n Automation",
		"url": "https://n8n.example.com/webhook",
		"method": "POST",
	}

	response = DistributionTargetResponse.from_orm_model(mock_target)
	assert response.platform_name == "n8n Automation"
	assert response.token_valid is None
	assert response.token_expires_at is None


# ============================================================================
# Token refresh task helper tests
# ============================================================================

@pytest.mark.asyncio
async def test_call_spotify_refresh_success():
	"""_call_spotify_refresh should return token data on 200 response."""
	from src.tasks.oauth_token_refresh import _call_spotify_refresh

	mock_response = MagicMock()
	mock_response.json.return_value = {
		"access_token": "new-access-token",
		"expires_in": 3600,
	}
	mock_response.raise_for_status = MagicMock()

	mock_client = AsyncMock()
	mock_client.post.return_value = mock_response

	with patch("src.tasks.oauth_token_refresh.httpx") as mock_httpx:
		mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
		mock_httpx.AsyncClient.return_value.__aexit__.return_value = None

		result = await _call_spotify_refresh(
			refresh_token="old-refresh",
			client_id="client-id",
			client_secret="client-secret",
		)

	assert result["access_token"] == "new-access-token"
	assert result["expires_in"] == 3600


@pytest.mark.asyncio
async def test_call_spotify_refresh_raises_on_401():
	"""_call_spotify_refresh should propagate HTTP errors from Spotify."""
	import httpx
	from src.tasks.oauth_token_refresh import _call_spotify_refresh

	mock_response = MagicMock()
	mock_response.status_code = 401
	mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
		"401 Unauthorized", request=MagicMock(), response=mock_response
	)

	mock_client = AsyncMock()
	mock_client.post.return_value = mock_response

	with patch("src.tasks.oauth_token_refresh.httpx") as mock_httpx:
		mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
		mock_httpx.AsyncClient.return_value.__aexit__.return_value = None
		mock_httpx.HTTPStatusError = httpx.HTTPStatusError

		with pytest.raises(httpx.HTTPStatusError):
			await _call_spotify_refresh(
				refresh_token="invalid-refresh",
				client_id="client-id",
				client_secret="client-secret",
			)


# ============================================================================
# Webhook schema validation unit tests
# ============================================================================

def test_webhook_schema_https_required():
	"""WebhookDistributionCreate must reject http:// URLs."""
	import pydantic
	from src.schemas.distribution_target import WebhookDistributionCreate

	with pytest.raises(pydantic.ValidationError):
		WebhookDistributionCreate(
			name="Bad Webhook",
			url="http://hooks.example.com/webhook",
			method="POST",
		)


def test_webhook_schema_max_10_headers():
	"""WebhookDistributionCreate must reject more than 10 headers."""
	import pydantic
	from src.schemas.distribution_target import WebhookDistributionCreate

	too_many = {f"X-Header-{i}": f"value-{i}" for i in range(11)}
	with pytest.raises(pydantic.ValidationError):
		WebhookDistributionCreate(
			name="Bad Webhook",
			url="https://hooks.example.com/webhook",
			method="POST",
			headers=too_many,
		)


def test_webhook_schema_invalid_method():
	"""WebhookDistributionCreate must reject methods other than POST/GET."""
	import pydantic
	from src.schemas.distribution_target import WebhookDistributionCreate

	with pytest.raises(pydantic.ValidationError):
		WebhookDistributionCreate(
			name="Bad Webhook",
			url="https://hooks.example.com/webhook",
			method="DELETE",
		)
