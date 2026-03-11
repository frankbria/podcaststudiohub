"""
Unit tests for credential encryption activation (GAP-035).

Tests:
- Webhook sensitive-header heuristic (_is_sensitive_header)
- _encrypt_webhook_headers / _decrypt_webhook_headers roundtrip
- create_webhook_target encrypts sensitive headers
- auth_service store_encrypted_api_key / get_decrypted_api_key
- auth_service returns None for missing provider
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(encrypted_map: dict | None = None):
	"""
	Return a mock AsyncSession whose execute() simulates pgcrypto by
	base64-encoding / decoding credential values.

	encrypted_map: {plaintext: ciphertext} — if provided, encrypt returns
	the mapped ciphertext and decrypt reverses it.  If None a simple
	reversible scheme (prepend 'ENC:') is used.
	"""
	import base64

	db = AsyncMock()

	async def fake_execute(stmt, params=None):
		if params is None:
			return MagicMock()
		result = MagicMock()
		text_str = str(stmt)

		if "encrypt_credential" in text_str:
			raw = params.get("credential", params.get("val", ""))
			encoded = "ENC:" + base64.b64encode(raw.encode()).decode()
			result.scalar_one.return_value = encoded
			result.scalar.return_value = encoded
		elif "decrypt_credential" in text_str:
			raw = params.get("encrypted_credential", params.get("val", ""))
			if raw.startswith("ENC:"):
				decoded = base64.b64decode(raw[4:]).decode()
			else:
				decoded = raw  # already plaintext (passthrough)
			result.scalar_one.return_value = decoded
			result.scalar.return_value = decoded
		return result

	db.execute = fake_execute
	db.commit = AsyncMock()
	db.refresh = AsyncMock()
	db.add = MagicMock()
	return db


# ---------------------------------------------------------------------------
# _is_sensitive_header
# ---------------------------------------------------------------------------

class TestIsSensitiveHeader:
	def test_authorization_header(self):
		from src.services.distribution_target_service import _is_sensitive_header
		assert _is_sensitive_header("Authorization") is True
		assert _is_sensitive_header("authorization") is True

	def test_secret_header(self):
		from src.services.distribution_target_service import _is_sensitive_header
		assert _is_sensitive_header("X-Secret-Key") is True
		assert _is_sensitive_header("x-webhook-secret") is True

	def test_token_header(self):
		from src.services.distribution_target_service import _is_sensitive_header
		assert _is_sensitive_header("X-Access-Token") is True

	def test_api_key_header(self):
		from src.services.distribution_target_service import _is_sensitive_header
		assert _is_sensitive_header("X-Api-Key") is True

	def test_innocuous_header(self):
		from src.services.distribution_target_service import _is_sensitive_header
		assert _is_sensitive_header("Content-Type") is False
		assert _is_sensitive_header("X-Custom-Header") is False
		assert _is_sensitive_header("Accept") is False


# ---------------------------------------------------------------------------
# _encrypt_webhook_headers / _decrypt_webhook_headers
# ---------------------------------------------------------------------------

class TestWebhookHeaderEncryption:
	@pytest.mark.asyncio
	async def test_sensitive_headers_encrypted(self):
		from src.services.distribution_target_service import _encrypt_webhook_headers
		db = _make_db()
		headers = {
			"Authorization": "Bearer my-secret-token",
			"Content-Type": "application/json",
		}
		result = await _encrypt_webhook_headers(db, headers)
		# Sensitive header value should be transformed
		assert result["Authorization"] != "Bearer my-secret-token"
		assert result["Authorization"].startswith("ENC:")
		# Non-sensitive header passes through unchanged
		assert result["Content-Type"] == "application/json"

	@pytest.mark.asyncio
	async def test_non_sensitive_headers_unchanged(self):
		from src.services.distribution_target_service import _encrypt_webhook_headers
		db = _make_db()
		headers = {"X-Request-ID": "abc123", "Accept": "application/json"}
		result = await _encrypt_webhook_headers(db, headers)
		assert result == headers

	@pytest.mark.asyncio
	async def test_roundtrip_encrypt_then_decrypt(self):
		from src.services.distribution_target_service import (
			_encrypt_webhook_headers,
			_decrypt_webhook_headers,
		)
		db = _make_db()
		original = {
			"Authorization": "Bearer secret",
			"X-Webhook-Secret": "mysecret",
			"Content-Type": "application/json",
		}
		encrypted = await _encrypt_webhook_headers(db, original)
		decrypted = await _decrypt_webhook_headers(db, encrypted)

		assert decrypted["Authorization"] == "Bearer secret"
		assert decrypted["X-Webhook-Secret"] == "mysecret"
		assert decrypted["Content-Type"] == "application/json"

	@pytest.mark.asyncio
	async def test_decrypt_handles_already_plaintext_gracefully(self):
		"""Decrypt should not crash on non-encrypted values (e.g. non-sensitive)."""
		from src.services.distribution_target_service import _decrypt_webhook_headers
		db = _make_db()
		headers = {"Content-Type": "application/json", "X-Custom": "value"}
		result = await _decrypt_webhook_headers(db, headers)
		assert result == headers

	@pytest.mark.asyncio
	async def test_empty_headers_returns_empty(self):
		from src.services.distribution_target_service import _encrypt_webhook_headers
		db = _make_db()
		result = await _encrypt_webhook_headers(db, {})
		assert result == {}


# ---------------------------------------------------------------------------
# create_webhook_target — encryption integration
# ---------------------------------------------------------------------------

class TestCreateWebhookTargetEncryption:
	@pytest.mark.asyncio
	async def test_sensitive_headers_stored_encrypted(self):
		from src.schemas.distribution_target import WebhookDistributionCreate
		from src.services.distribution_target_service import create_webhook_target

		db = _make_db()
		webhook_data = WebhookDistributionCreate(
			name="Test Webhook",
			url="https://hooks.example.com/notify",
			method="POST",
			headers={"Authorization": "Bearer plaintext-token"},
		)

		# Capture the DistributionTarget passed to db.add
		added_targets = []
		db.add = lambda obj: added_targets.append(obj)

		await create_webhook_target(db, uuid4(), uuid4(), webhook_data)

		assert len(added_targets) == 1
		stored_headers = added_targets[0].config.get("headers", {})
		# The stored value must not be the original plaintext
		assert stored_headers.get("Authorization") != "Bearer plaintext-token"
		assert stored_headers.get("Authorization", "").startswith("ENC:")

	@pytest.mark.asyncio
	async def test_webhook_without_headers_stores_no_headers(self):
		from src.schemas.distribution_target import WebhookDistributionCreate
		from src.services.distribution_target_service import create_webhook_target

		db = _make_db()
		webhook_data = WebhookDistributionCreate(
			name="No Headers",
			url="https://hooks.example.com/notify",
			method="POST",
		)
		added_targets = []
		db.add = lambda obj: added_targets.append(obj)

		await create_webhook_target(db, uuid4(), uuid4(), webhook_data)
		assert "headers" not in added_targets[0].config

	@pytest.mark.asyncio
	async def test_non_sensitive_headers_stored_as_plaintext(self):
		from src.schemas.distribution_target import WebhookDistributionCreate
		from src.services.distribution_target_service import create_webhook_target

		db = _make_db()
		webhook_data = WebhookDistributionCreate(
			name="Custom Headers",
			url="https://hooks.example.com/notify",
			method="POST",
			headers={"Content-Type": "application/json", "X-Custom": "myvalue"},
		)
		added_targets = []
		db.add = lambda obj: added_targets.append(obj)

		await create_webhook_target(db, uuid4(), uuid4(), webhook_data)
		stored_headers = added_targets[0].config.get("headers", {})
		assert stored_headers.get("Content-Type") == "application/json"
		assert stored_headers.get("X-Custom") == "myvalue"


# ---------------------------------------------------------------------------
# auth_service — store_encrypted_api_key / get_decrypted_api_key
# ---------------------------------------------------------------------------

class TestAuthServiceApiKeyEncryption:
	def _make_user(self, existing_keys: dict | None = None):
		user = MagicMock()
		user.id = uuid4()
		user.encrypted_api_keys = dict(existing_keys or {})
		return user

	@pytest.mark.asyncio
	async def test_store_encrypts_api_key(self):
		from src.services.auth_service import store_encrypted_api_key

		db = _make_db()
		user = self._make_user()

		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=user),
		):
			await store_encrypted_api_key(db, user.id, "openai", "sk-plaintext-key")

		# The stored value should be encrypted, not the original
		stored = user.encrypted_api_keys.get("openai", "")
		assert stored != "sk-plaintext-key"
		assert stored.startswith("ENC:")

	@pytest.mark.asyncio
	async def test_store_raises_for_missing_user(self):
		from src.services.auth_service import store_encrypted_api_key

		db = _make_db()
		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=None),
		):
			with pytest.raises(ValueError, match="not found"):
				await store_encrypted_api_key(db, uuid4(), "openai", "sk-key")

	@pytest.mark.asyncio
	async def test_retrieve_decrypts_api_key(self):
		import base64
		from src.services.auth_service import get_decrypted_api_key

		plaintext = "sk-my-real-key"
		encrypted = "ENC:" + base64.b64encode(plaintext.encode()).decode()
		user = self._make_user({"openai": encrypted})
		db = _make_db()

		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=user),
		):
			result = await get_decrypted_api_key(db, user.id, "openai")

		assert result == plaintext

	@pytest.mark.asyncio
	async def test_retrieve_returns_none_for_missing_provider(self):
		from src.services.auth_service import get_decrypted_api_key

		user = self._make_user({"openai": "ENC:abc"})
		db = _make_db()

		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=user),
		):
			result = await get_decrypted_api_key(db, user.id, "elevenlabs")

		assert result is None

	@pytest.mark.asyncio
	async def test_retrieve_returns_none_for_missing_user(self):
		from src.services.auth_service import get_decrypted_api_key

		db = _make_db()
		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=None),
		):
			result = await get_decrypted_api_key(db, uuid4(), "openai")

		assert result is None

	@pytest.mark.asyncio
	async def test_store_preserves_existing_keys(self):
		"""Storing a new key should not overwrite other providers."""
		import base64
		from src.services.auth_service import store_encrypted_api_key

		existing_enc = "ENC:" + base64.b64encode(b"existing-key").decode()
		user = self._make_user({"elevenlabs": existing_enc})
		db = _make_db()

		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=user),
		):
			await store_encrypted_api_key(db, user.id, "openai", "sk-new-key")

		# Both keys should be present
		assert "elevenlabs" in user.encrypted_api_keys
		assert "openai" in user.encrypted_api_keys
		assert user.encrypted_api_keys["elevenlabs"] == existing_enc

	@pytest.mark.asyncio
	async def test_roundtrip_store_then_retrieve(self):
		"""Full roundtrip: store plaintext, retrieve decrypts correctly."""
		from src.services.auth_service import store_encrypted_api_key, get_decrypted_api_key

		user = self._make_user()
		db = _make_db()

		with patch(
			"src.services.auth_service.get_user_by_id",
			new=AsyncMock(return_value=user),
		):
			await store_encrypted_api_key(db, user.id, "gemini", "AIza-secret")
			result = await get_decrypted_api_key(db, user.id, "gemini")

		assert result == "AIza-secret"
