"""
Unit tests for database.py — covers branches that don't need a real DB.

Tests cover:
- _get_sync_engine: raises ValueError for non-asyncpg URLs
- set_tenant_context: raises ValueError for invalid/empty UUID strings
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import src.database as db_module


# ---------------------------------------------------------------------------
# _get_sync_engine
# ---------------------------------------------------------------------------

class TestGetSyncEngine:
	def test_non_asyncpg_url_raises_value_error(self):
		"""_get_sync_engine must reject non-asyncpg DATABASE_URL values."""
		original = db_module._sync_engine
		db_module._sync_engine = None  # force re-initialisation

		try:
			mock_settings = MagicMock()
			mock_settings.DATABASE_URL = "sqlite:///test.db"
			mock_settings.DEBUG = False
			mock_settings.DATABASE_POOL_SIZE = 5
			mock_settings.DATABASE_MAX_OVERFLOW = 10
			with patch("src.database.settings", mock_settings):
				with pytest.raises(ValueError, match="postgresql\\+asyncpg"):
					db_module._get_sync_engine()
		finally:
			db_module._sync_engine = original

	def test_wrong_scheme_raises_value_error(self):
		"""postgres:// (no +asyncpg driver) also raises ValueError."""
		original = db_module._sync_engine
		db_module._sync_engine = None

		try:
			mock_settings = MagicMock()
			mock_settings.DATABASE_URL = "postgresql://x:x@localhost/db"
			mock_settings.DEBUG = False
			mock_settings.DATABASE_POOL_SIZE = 5
			mock_settings.DATABASE_MAX_OVERFLOW = 10
			with patch("src.database.settings", mock_settings):
				with pytest.raises(ValueError):
					db_module._get_sync_engine()
		finally:
			db_module._sync_engine = original


# ---------------------------------------------------------------------------
# set_tenant_context
# ---------------------------------------------------------------------------

class TestSetTenantContext:
	@pytest.mark.asyncio
	async def test_invalid_uuid_string_raises_value_error(self):
		"""Non-UUID string must raise ValueError to prevent SQL injection."""
		session = AsyncMock()
		with pytest.raises(ValueError, match="Invalid tenant_id format"):
			await db_module.set_tenant_context(session, "not-a-uuid")

	@pytest.mark.asyncio
	async def test_empty_string_raises_value_error(self):
		"""Empty string is not a valid UUID and must raise ValueError."""
		session = AsyncMock()
		with pytest.raises(ValueError, match="Invalid tenant_id format"):
			await db_module.set_tenant_context(session, "")

	@pytest.mark.asyncio
	async def test_valid_uuid_executes_set_local(self):
		"""Valid UUID string should execute the SET LOCAL statement."""
		session = AsyncMock()
		import uuid
		valid_uuid = str(uuid.uuid4())
		await db_module.set_tenant_context(session, valid_uuid)
		session.execute.assert_called_once()
		# Verify the UUID appears in the SQL text
		call_args = session.execute.call_args
		sql_text = str(call_args[0][0])
		assert valid_uuid in sql_text
