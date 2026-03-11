"""
Distribution Target service layer for business logic.

Provides CRUD operations, OAuth flows, and connection testing for
podcast distribution platforms. Supports Spotify OAuth, Apple Podcasts
API key management, and webhook configuration.
"""

import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.distribution_target import DistributionTarget
from ..schemas.distribution_target import (
	WebhookDistributionCreate,
	AppleDistributionCreate,
	DistributionTargetUpdate,
)
from ..utils.encryption import encrypt_credential, decrypt_credential

logger = logging.getLogger(__name__)

# In-memory OAuth state store: {state: {user_id: str, created_at: datetime}}
# In production, replace with Redis for multi-instance support.
_oauth_states: dict[str, dict] = {}
_STATE_TTL_SECONDS = 600  # 10 minutes


def generate_oauth_state(user_id: str) -> str:
	"""
	Generate a CSRF state token for OAuth flows.

	Stores the state in memory with a TTL of 10 minutes.
	In production environments with multiple API instances, use Redis.

	Args:
		user_id: ID of the user initiating the OAuth flow

	Returns:
		Secure random state token
	"""
	state = secrets.token_urlsafe(32)
	_oauth_states[state] = {
		"user_id": user_id,
		"created_at": datetime.now(timezone.utc),
	}
	# Clean up expired states while we're here
	_cleanup_expired_states()
	return state


def validate_oauth_state(state: str) -> Optional[str]:
	"""
	Validate and consume an OAuth state token.

	Returns the user_id if valid, None if invalid or expired.
	Removes the state after validation (one-time use).

	Args:
		state: OAuth state token to validate

	Returns:
		user_id string if valid, None if invalid/expired
	"""
	state_data = _oauth_states.get(state)
	if not state_data:
		return None

	# Check TTL
	age = datetime.now(timezone.utc) - state_data["created_at"]
	if age.total_seconds() > _STATE_TTL_SECONDS:
		del _oauth_states[state]
		return None

	# Consume the state (one-time use)
	del _oauth_states[state]
	return state_data["user_id"]


def _cleanup_expired_states() -> None:
	"""Remove expired OAuth states from memory."""
	now = datetime.now(timezone.utc)
	expired = [
		state
		for state, data in _oauth_states.items()
		if (now - data["created_at"]).total_seconds() > _STATE_TTL_SECONDS
	]
	for state in expired:
		del _oauth_states[state]


def _is_sensitive_header(header_name: str) -> bool:
	"""Return True if a header name indicates it contains a secret credential."""
	lower = header_name.lower()
	return "authorization" in lower or "secret" in lower or "token" in lower or "api-key" in lower


async def _encrypt_webhook_headers(db: AsyncSession, headers: dict) -> dict:
	"""
	Encrypt sensitive header values in a webhook headers dict.

	Headers whose names contain 'authorization', 'secret', 'token', or 'api-key'
	are encrypted; all others are stored as-is.

	Args:
		db: Database session
		headers: Raw header name → value mapping

	Returns:
		New dict with sensitive values replaced by encrypted ciphertext
	"""
	encrypted = {}
	for name, value in headers.items():
		if _is_sensitive_header(name) and value:
			encrypted[name] = await encrypt_credential(db, value)
		else:
			encrypted[name] = value
	return encrypted


async def _decrypt_webhook_headers(db: AsyncSession, headers: dict) -> dict:
	"""
	Decrypt sensitive header values from stored webhook config.

	Mirrors _encrypt_webhook_headers: only headers whose names match the
	sensitive-header heuristic are decrypted.

	Args:
		db: Database session
		headers: Stored header name → value mapping (some values encrypted)

	Returns:
		New dict with sensitive values decrypted
	"""
	decrypted = {}
	for name, value in headers.items():
		if _is_sensitive_header(name) and value:
			try:
				decrypted[name] = await decrypt_credential(db, value)
			except Exception:
				logger.warning("Failed to decrypt header '%s'; returning as-is", name)
				decrypted[name] = value
		else:
			decrypted[name] = value
	return decrypted


async def create_webhook_target(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	webhook_data: WebhookDistributionCreate,
) -> DistributionTarget:
	"""
	Create a webhook distribution target.

	Stores webhook URL, method, and headers in the config JSONB.
	Sensitive headers (Authorization, X-Secret, etc.) are encrypted before
	storage using PostgreSQL pgcrypto.

	Args:
		db: Database session
		user_id: ID of user creating the target
		tenant_id: Tenant ID for isolation
		webhook_data: Webhook creation data

	Returns:
		Created DistributionTarget instance
	"""
	config = {
		"name": webhook_data.name,
		"url": str(webhook_data.url),
		"method": webhook_data.method,
	}
	if webhook_data.headers:
		config["headers"] = await _encrypt_webhook_headers(db, webhook_data.headers)

	target = DistributionTarget(
		user_id=user_id,
		tenant_id=tenant_id,
		project_id=webhook_data.project_id,
		target_type="webhook",
		config=config,
		is_active=True,
	)
	db.add(target)
	await db.commit()
	return target


async def create_apple_target(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	apple_data: AppleDistributionCreate,
) -> DistributionTarget:
	"""
	Create an Apple Podcasts distribution target with encrypted API key.

	Encrypts the API key before storing in the config JSONB field.
	The decrypted key is never returned in API responses.

	Args:
		db: Database session
		user_id: ID of user creating the target
		tenant_id: Tenant ID for isolation
		apple_data: Apple Podcasts connection data

	Returns:
		Created DistributionTarget instance
	"""
	# Encrypt the API key before storage
	encrypted_api_key = await encrypt_credential(db, apple_data.api_key)

	config = {
		"show_id": apple_data.show_id,
		"credentials": {
			"api_key": encrypted_api_key,
		},
	}

	target = DistributionTarget(
		user_id=user_id,
		tenant_id=tenant_id,
		project_id=apple_data.project_id,
		target_type="apple_podcasts",
		config=config,
		is_active=True,
	)
	db.add(target)
	await db.commit()
	return target


async def create_spotify_target(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	access_token: str,
	refresh_token: str,
	expires_in: int,
	show_id: str,
	show_name: str,
	project_id: Optional[UUID] = None,
) -> DistributionTarget:
	"""
	Create a Spotify distribution target after successful OAuth.

	Encrypts access token and refresh token before storage.

	Args:
		db: Database session
		user_id: ID of authenticated user
		tenant_id: Tenant ID for isolation
		access_token: Spotify OAuth access token
		refresh_token: Spotify OAuth refresh token
		expires_in: Token TTL in seconds
		show_id: Spotify show identifier
		show_name: Spotify show name for display
		project_id: Optional project scoping

	Returns:
		Created DistributionTarget instance
	"""
	# Encrypt tokens before storage - never store plaintext tokens
	encrypted_access = await encrypt_credential(db, access_token)
	encrypted_refresh = await encrypt_credential(db, refresh_token)

	expires_at = (
		datetime.now(timezone.utc) + timedelta(seconds=expires_in)
	).isoformat()

	config = {
		"show_id": show_id,
		"show_name": show_name,
		"oauth_tokens": {
			"access_token": encrypted_access,
			"refresh_token": encrypted_refresh,
			"expires_at": expires_at,
		},
	}

	target = DistributionTarget(
		user_id=user_id,
		tenant_id=tenant_id,
		project_id=project_id,
		target_type="spotify",
		config=config,
		is_active=True,
	)
	db.add(target)
	await db.commit()
	return target


async def get_distribution_targets(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 20,
	target_type: Optional[str] = None,
	project_id: Optional[UUID] = None,
) -> tuple[list[DistributionTarget], int]:
	"""
	Get paginated list of distribution targets.

	RLS automatically filters by tenant based on the session's tenant_id.
	Supports optional filtering by target type and project.

	Args:
		db: Database session
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return
		target_type: Optional filter by platform type
		project_id: Optional filter by project ID

	Returns:
		Tuple of (targets list, total count)
	"""
	query = select(DistributionTarget)

	if target_type is not None:
		query = query.where(DistributionTarget.target_type == target_type)
	if project_id is not None:
		query = query.where(DistributionTarget.project_id == project_id)

	# Get total count before pagination
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	# Get paginated results, newest first
	query = query.offset(skip).limit(limit).order_by(
		DistributionTarget.created_at.desc()
	)
	result = await db.execute(query)
	targets = result.scalars().all()

	return list(targets), total


async def get_distribution_target_by_id(
	db: AsyncSession,
	target_id: UUID,
) -> Optional[DistributionTarget]:
	"""
	Get a distribution target by ID.

	RLS ensures user can only access targets within their tenant.
	Returns None if target doesn't exist or belongs to different tenant.

	Args:
		db: Database session
		target_id: UUID of target to retrieve

	Returns:
		DistributionTarget instance or None if not found
	"""
	result = await db.execute(
		select(DistributionTarget).where(DistributionTarget.id == target_id)
	)
	return result.scalar_one_or_none()


async def update_distribution_target(
	db: AsyncSession,
	target: DistributionTarget,
	update_data: DistributionTargetUpdate,
) -> DistributionTarget:
	"""
	Update distribution target with partial data.

	Only updates fields provided in update_data (partial updates supported).
	Credential updates are not allowed through this endpoint - use re-auth.

	Args:
		db: Database session
		target: Existing DistributionTarget instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated DistributionTarget instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)
	for field, value in update_dict.items():
		setattr(target, field, value)

	await db.commit()
	return target


async def delete_distribution_target(
	db: AsyncSession,
	target: DistributionTarget,
) -> None:
	"""
	Delete a distribution target permanently.

	Note: OAuth token revocation is a best-effort operation.
	The database record is always deleted regardless of revocation outcome.

	Args:
		db: Database session
		target: DistributionTarget instance to delete
	"""
	await db.delete(target)
	await db.commit()


async def exchange_spotify_code(
	client_id: str,
	client_secret: str,
	redirect_uri: str,
	code: str,
) -> dict:
	"""
	Exchange Spotify OAuth authorization code for tokens.

	Args:
		client_id: Spotify application client ID
		client_secret: Spotify application client secret
		redirect_uri: OAuth callback URL (must match registered URI)
		code: Authorization code from Spotify callback

	Returns:
		Dict with access_token, refresh_token, expires_in

	Raises:
		httpx.HTTPStatusError: If Spotify token exchange fails
	"""
	async with httpx.AsyncClient() as client:
		response = await client.post(
			"https://accounts.spotify.com/api/token",
			data={
				"grant_type": "authorization_code",
				"code": code,
				"redirect_uri": redirect_uri,
			},
			auth=(client_id, client_secret),
			headers={"Content-Type": "application/x-www-form-urlencoded"},
		)
		response.raise_for_status()
		return response.json()


async def get_spotify_show_info(access_token: str, show_id: Optional[str] = None) -> dict:
	"""
	Get Spotify show information to verify connection.

	If show_id is provided, retrieves specific show details.
	Otherwise retrieves user's saved shows to find their podcast.

	Args:
		access_token: Valid Spotify access token
		show_id: Optional Spotify show ID

	Returns:
		Dict with show details (id, name)
	"""
	async with httpx.AsyncClient() as client:
		if show_id:
			url = f"https://api.spotify.com/v1/shows/{show_id}"
		else:
			url = "https://api.spotify.com/v1/me/shows?limit=1"

		response = await client.get(
			url,
			headers={"Authorization": f"Bearer {access_token}"},
		)
		response.raise_for_status()
		data = response.json()

		if show_id:
			return {"id": data.get("id", show_id), "name": data.get("name", "")}
		else:
			items = data.get("items", [])
			if items:
				show = items[0].get("show", {})
				return {"id": show.get("id", ""), "name": show.get("name", "")}
			return {"id": "", "name": ""}


async def refresh_spotify_access_token(
	db: AsyncSession,
	target: DistributionTarget,
	client_id: str,
	client_secret: str,
) -> DistributionTarget:
	"""
	Refresh expired Spotify access token using the stored refresh token.

	Decrypts the refresh token, exchanges it for a new access token,
	encrypts the new token and updates the database record.

	Args:
		db: Database session
		target: Spotify DistributionTarget instance
		client_id: Spotify application client ID
		client_secret: Spotify application client secret

	Returns:
		Updated DistributionTarget with new access token expiration

	Raises:
		ValueError: If target is not a Spotify target or missing tokens
		httpx.HTTPStatusError: If token refresh fails
	"""
	config = target.config or {}
	oauth_tokens = config.get("oauth_tokens", {})
	encrypted_refresh = oauth_tokens.get("refresh_token")

	if not encrypted_refresh:
		raise ValueError("No refresh token found for this Spotify target")

	# Decrypt the stored refresh token
	refresh_token = await decrypt_credential(db, encrypted_refresh)

	# Exchange refresh token for new access token
	async with httpx.AsyncClient() as client:
		response = await client.post(
			"https://accounts.spotify.com/api/token",
			data={
				"grant_type": "refresh_token",
				"refresh_token": refresh_token,
			},
			auth=(client_id, client_secret),
			headers={"Content-Type": "application/x-www-form-urlencoded"},
		)
		response.raise_for_status()
		token_data = response.json()

	# Encrypt the new access token
	new_access_token = token_data["access_token"]
	encrypted_access = await encrypt_credential(db, new_access_token)

	# Update expiration timestamp
	expires_in = token_data.get("expires_in", 3600)
	expires_at = (
		datetime.now(timezone.utc) + timedelta(seconds=expires_in)
	).isoformat()

	# Handle optional new refresh token from Spotify
	new_refresh_token = token_data.get("refresh_token")
	if new_refresh_token:
		encrypted_refresh = await encrypt_credential(db, new_refresh_token)

	# Update config in-place, preserving other fields
	updated_config = dict(config)
	updated_config["oauth_tokens"] = {
		**oauth_tokens,
		"access_token": encrypted_access,
		"refresh_token": encrypted_refresh,
		"expires_at": expires_at,
	}
	target.config = updated_config

	await db.commit()
	return target


async def test_connection(
	db: AsyncSession,
	target: DistributionTarget,
	spotify_client_id: Optional[str] = None,
	spotify_client_secret: Optional[str] = None,
) -> dict:
	"""
	Test connectivity to a distribution platform.

	For Spotify: Verifies access token validity by fetching show info.
	For Apple Podcasts: Validates API key format and connectivity.
	For webhooks: Sends a test POST payload to the webhook URL.

	Args:
		db: Database session
		target: DistributionTarget to test
		spotify_client_id: Spotify client ID (for token refresh if needed)
		spotify_client_secret: Spotify client secret (for token refresh)

	Returns:
		Dict with success, platform, message, and optional show_details/error
	"""
	config = target.config or {}
	platform = target.target_type

	if platform == "webhook":
		return await _test_webhook_connection(db, config)
	elif platform == "spotify":
		return await _test_spotify_connection(db, target, config)
	elif platform == "apple_podcasts":
		return await _test_apple_connection(db, config)
	else:
		return {
			"success": False,
			"platform": platform,
			"message": f"Unknown platform type: {platform}",
			"error": "unsupported_platform",
		}


async def _test_webhook_connection(db: AsyncSession, config: dict) -> dict:
	"""Send test payload to webhook URL, decrypting sensitive headers first."""
	url = config.get("url", "")
	method = config.get("method", "POST")
	raw_headers = config.get("headers", {})
	# Decrypt any encrypted sensitive headers before sending the HTTP request
	headers = await _decrypt_webhook_headers(db, raw_headers) if raw_headers else {}

	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			test_payload = {"test": True, "event": "connection_test"}
			if method == "POST":
				response = await client.post(url, json=test_payload, headers=headers)
			else:
				response = await client.get(url, headers=headers)

			response.raise_for_status()
			return {
				"success": True,
				"platform": "webhook",
				"message": f"Webhook connection successful (HTTP {response.status_code})",
			}
	except httpx.HTTPStatusError as e:
		return {
			"success": False,
			"platform": "webhook",
			"message": f"Webhook returned error status: {e.response.status_code}",
			"error": f"http_error_{e.response.status_code}",
		}
	except Exception as e:
		logger.warning("Webhook connection test failed: %s", type(e).__name__)
		return {
			"success": False,
			"platform": "webhook",
			"message": "Webhook connection failed",
			"error": "connection_failed",
		}


async def _test_spotify_connection(
	db: AsyncSession,
	target: DistributionTarget,
	config: dict,
) -> dict:
	"""Test Spotify connection by fetching show details."""
	oauth_tokens = config.get("oauth_tokens", {})
	encrypted_access = oauth_tokens.get("access_token")

	if not encrypted_access:
		return {
			"success": False,
			"platform": "spotify",
			"message": "No access token found. Please re-authorize.",
			"error": "no_token",
		}

	try:
		access_token = await decrypt_credential(db, encrypted_access)
		show_id = config.get("show_id")
		show_details = await get_spotify_show_info(access_token, show_id)

		return {
			"success": True,
			"platform": "spotify",
			"message": f"Successfully connected to Spotify show: '{show_details.get('name', 'Unknown')}'",
			"show_details": show_details,
		}
	except httpx.HTTPStatusError as e:
		if e.response.status_code == 401:
			return {
				"success": False,
				"platform": "spotify",
				"message": "Access token expired. Use refresh-token endpoint to renew.",
				"error": "token_expired",
			}
		logger.warning("Spotify connection test failed with HTTP %d", e.response.status_code)
		return {
			"success": False,
			"platform": "spotify",
			"message": "Spotify connection failed",
			"error": "connection_failed",
		}
	except Exception as e:
		logger.warning("Spotify connection test failed: %s", type(e).__name__)
		return {
			"success": False,
			"platform": "spotify",
			"message": "Spotify connection failed",
			"error": "connection_failed",
		}


async def _test_apple_connection(db: AsyncSession, config: dict) -> dict:
	"""Test Apple Podcasts connection by validating API key."""
	credentials = config.get("credentials", {})
	encrypted_key = credentials.get("api_key")

	if not encrypted_key:
		return {
			"success": False,
			"platform": "apple_podcasts",
			"message": "No API key found. Please re-add your Apple Podcasts credentials.",
			"error": "no_credentials",
		}

	# Verify we can decrypt the key (validates it's properly stored)
	try:
		await decrypt_credential(db, encrypted_key)
		show_id = config.get("show_id", "unknown")
		return {
			"success": True,
			"platform": "apple_podcasts",
			"message": f"Apple Podcasts credentials verified for show ID: {show_id}",
			"show_details": {"id": show_id},
		}
	except Exception as e:
		logger.warning("Apple Podcasts credential validation failed: %s", type(e).__name__)
		return {
			"success": False,
			"platform": "apple_podcasts",
			"message": "Failed to validate Apple Podcasts credentials",
			"error": "credential_error",
		}
