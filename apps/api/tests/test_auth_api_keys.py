"""
Test suite for user API key encryption service functions.

Tests store, retrieve, delete, and list operations for encrypted
API keys stored in the user's encrypted_api_keys JSONB column.
"""

import pytest
from uuid import uuid4
from fastapi import HTTPException

from src.services.auth_service import (
	create_user,
	store_api_key,
	get_api_key,
	delete_api_key,
	list_api_key_providers,
)


@pytest.fixture
async def test_user(test_db):
	"""Create a test user and return the User model instance."""
	user = await create_user(
		session=test_db,
		email=f"apikey_test_{uuid4()}@example.com",
		password="SecurePass123!",
		full_name="API Key Test User",
	)
	return user


@pytest.mark.asyncio
async def test_store_and_retrieve_api_key(test_db, test_user):
	"""Store an OpenAI key, retrieve it, verify it matches."""
	original_key = "sk-test-openai-key-1234567890"

	await store_api_key(test_db, test_user.id, "openai", original_key)

	retrieved = await get_api_key(test_db, test_user.id, "openai")
	assert retrieved == original_key


@pytest.mark.asyncio
async def test_retrieve_nonexistent_provider(test_db, test_user):
	"""Returns None for a provider that has no stored key."""
	result = await get_api_key(test_db, test_user.id, "nonexistent_provider")
	assert result is None


@pytest.mark.asyncio
async def test_delete_api_key(test_db, test_user):
	"""Store a key, delete it, verify it's gone."""
	await store_api_key(test_db, test_user.id, "elevenlabs", "el-key-abc")

	deleted = await delete_api_key(test_db, test_user.id, "elevenlabs")
	assert deleted is True

	retrieved = await get_api_key(test_db, test_user.id, "elevenlabs")
	assert retrieved is None


@pytest.mark.asyncio
async def test_delete_nonexistent_provider(test_db, test_user):
	"""Returns False when deleting a provider that was never stored."""
	result = await delete_api_key(test_db, test_user.id, "never_stored")
	assert result is False


@pytest.mark.asyncio
async def test_list_providers(test_db, test_user):
	"""Store multiple keys, list returns correct provider names."""
	await store_api_key(test_db, test_user.id, "openai", "sk-openai-key")
	await store_api_key(test_db, test_user.id, "elevenlabs", "el-key")
	await store_api_key(test_db, test_user.id, "gemini", "gem-key")

	providers = await list_api_key_providers(test_db, test_user.id)
	assert sorted(providers) == ["elevenlabs", "gemini", "openai"]


@pytest.mark.asyncio
async def test_store_api_key_user_not_found(test_db):
	"""Raises HTTPException(404) for nonexistent user."""
	fake_user_id = uuid4()
	with pytest.raises(HTTPException) as exc_info:
		await store_api_key(test_db, fake_user_id, "openai", "sk-key")
	assert exc_info.value.status_code == 404
