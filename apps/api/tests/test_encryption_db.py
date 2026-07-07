"""
Integration tests for the DB-dependent credential encryption helpers.

encrypt_credential / decrypt_credential / decrypt_credential_sync /
encrypt_api_keys / decrypt_api_keys all delegate to PostgreSQL pgcrypto
functions (encrypt_credential/decrypt_credential SQL functions provisioned by
migration 001_initial_schema.py). Per project policy these are tested against
a real database rather than mocked.
"""

import pytest

from src.database import SyncSessionLocal
from src.utils.encryption import (
	decrypt_api_keys,
	decrypt_credential,
	decrypt_credential_sync,
	encrypt_api_keys,
	encrypt_credential,
)


# ============================================================================
# encrypt_credential / decrypt_credential (async round trip)
# ============================================================================


@pytest.mark.asyncio
async def test_encrypt_credential_returns_ciphertext_different_from_plaintext(test_db):
	plaintext = "sk-super-secret-api-key-12345"

	encrypted = await encrypt_credential(test_db, plaintext)

	assert isinstance(encrypted, str)
	assert encrypted != plaintext


@pytest.mark.asyncio
async def test_decrypt_credential_round_trips_encrypted_value(test_db):
	plaintext = "sk-super-secret-api-key-12345"

	encrypted = await encrypt_credential(test_db, plaintext)
	decrypted = await decrypt_credential(test_db, encrypted)

	assert decrypted == plaintext


@pytest.mark.asyncio
async def test_encrypt_credential_is_nondeterministic(test_db):
	"""pgcrypto's pgp_sym_encrypt salts its output, so encrypting the same
	plaintext twice should not yield identical ciphertext."""
	plaintext = "another-secret-value"

	encrypted_1 = await encrypt_credential(test_db, plaintext)
	encrypted_2 = await encrypt_credential(test_db, plaintext)

	assert encrypted_1 != encrypted_2
	assert await decrypt_credential(test_db, encrypted_1) == plaintext
	assert await decrypt_credential(test_db, encrypted_2) == plaintext


# ============================================================================
# encrypt_api_keys / decrypt_api_keys (async, dict of multiple keys)
# ============================================================================


@pytest.mark.asyncio
async def test_encrypt_api_keys_encrypts_each_present_value(test_db):
	api_keys = {
		"openai_api_key": "sk-openai-123",
		"elevenlabs_api_key": "el-456",
	}

	encrypted = await encrypt_api_keys(test_db, api_keys)

	assert set(encrypted.keys()) == set(api_keys.keys())
	for key_name, plaintext in api_keys.items():
		assert encrypted[key_name] != plaintext


@pytest.mark.asyncio
async def test_encrypt_api_keys_skips_falsy_values(test_db):
	"""Keys with empty/None values must not be sent to pgcrypto or included
	in the returned dict (the `if key_value:` guard in encrypt_api_keys)."""
	api_keys = {
		"openai_api_key": "sk-openai-123",
		"gemini_api_key": "",
		"custom_api_key": None,
	}

	encrypted = await encrypt_api_keys(test_db, api_keys)

	assert "openai_api_key" in encrypted
	assert "gemini_api_key" not in encrypted
	assert "custom_api_key" not in encrypted


@pytest.mark.asyncio
async def test_decrypt_api_keys_round_trips_multiple_keys(test_db):
	api_keys = {
		"openai_api_key": "sk-openai-123",
		"elevenlabs_api_key": "el-456",
	}

	encrypted = await encrypt_api_keys(test_db, api_keys)
	decrypted = await decrypt_api_keys(test_db, encrypted)

	assert decrypted == api_keys


@pytest.mark.asyncio
async def test_decrypt_api_keys_skips_falsy_values(test_db):
	encrypted_keys = {
		"openai_api_key": await encrypt_credential(test_db, "sk-openai-123"),
		"gemini_api_key": "",
		"custom_api_key": None,
	}

	decrypted = await decrypt_api_keys(test_db, encrypted_keys)

	assert decrypted == {"openai_api_key": "sk-openai-123"}


# ============================================================================
# decrypt_credential_sync (synchronous Session — used by Celery tasks)
# ============================================================================


@pytest.mark.asyncio
async def test_decrypt_credential_sync_round_trips_value_from_sync_session(test_db):
	"""Encrypt via the async session (as the web app would), then decrypt via
	a plain synchronous Session (as a Celery task would) and confirm the
	round trip yields the original plaintext."""
	plaintext = "sk-celery-task-secret"
	encrypted = await encrypt_credential(test_db, plaintext)

	sync_db = SyncSessionLocal()
	try:
		decrypted = decrypt_credential_sync(sync_db, encrypted)
	finally:
		sync_db.close()

	assert decrypted == plaintext
