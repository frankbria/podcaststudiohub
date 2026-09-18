"""
Unit tests for dependencies.py — no DB or Redis needed.

Tests cover:
- get_current_tenant: valid UUID, missing tenant_id, invalid UUID format
- create_rate_limit_dependency: rate limiting disabled, allowed request, blocked request
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Minimal request stub (matches pattern in test_tenant_isolation.py)
# ---------------------------------------------------------------------------

class _State:
	pass


class MockRequest:
	def __init__(self, tenant_id=None, client_host="127.0.0.1", forwarded_for=None):
		self.state = _State()
		if tenant_id is not None:
			self.state.tenant_id = tenant_id
		self.client = MagicMock()
		self.client.host = client_host
		self.headers = {}
		if forwarded_for:
			self.headers["X-Forwarded-For"] = forwarded_for


# ---------------------------------------------------------------------------
# get_current_tenant
# ---------------------------------------------------------------------------

class TestGetCurrentTenant:
	def test_valid_uuid_returns_uuid_object(self):
		from src.dependencies import get_current_tenant
		uid = str(uuid4())
		request = MockRequest(tenant_id=uid)
		result = get_current_tenant(request)
		assert isinstance(result, UUID)
		assert str(result) == uid

	def test_missing_tenant_id_raises_401(self):
		from src.dependencies import get_current_tenant
		request = MockRequest()  # no tenant_id in state
		with pytest.raises(HTTPException) as exc_info:
			get_current_tenant(request)
		assert exc_info.value.status_code == 401

	def test_none_tenant_id_raises_401(self):
		from src.dependencies import get_current_tenant
		request = MockRequest(tenant_id=None)
		# state.tenant_id is None (falsy)
		with pytest.raises(HTTPException) as exc_info:
			get_current_tenant(request)
		assert exc_info.value.status_code == 401

	def test_invalid_uuid_string_raises_401(self):
		from src.dependencies import get_current_tenant
		request = MockRequest(tenant_id="not-a-uuid-at-all")
		with pytest.raises(HTTPException) as exc_info:
			get_current_tenant(request)
		assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# create_rate_limit_dependency
# ---------------------------------------------------------------------------

class TestCreateRateLimitDependency:
	@pytest.mark.asyncio
	async def test_disabled_returns_immediately(self):
		"""When RATE_LIMIT_ENABLED=False, the dependency does nothing."""
		from src.dependencies import create_rate_limit_dependency
		dep = create_rate_limit_dependency("test", 10, 1)
		request = MockRequest()

		mock_settings = MagicMock()
		mock_settings.RATE_LIMIT_ENABLED = False

		# The closure does `from src.config import settings` on each call,
		# so patching the module-level attribute is sufficient.
		with patch("src.config.settings", mock_settings):
			# Should complete without raising
			await dep(request)

	@pytest.mark.asyncio
	async def test_allowed_request_does_not_raise(self):
		"""When limiter.is_allowed returns (True, ...), no exception is raised."""
		from src.dependencies import create_rate_limit_dependency
		dep = create_rate_limit_dependency("login", 5, 1)
		request = MockRequest(client_host="10.0.0.1")

		mock_settings = MagicMock()
		mock_settings.RATE_LIMIT_ENABLED = True
		mock_settings.REDIS_URL = "redis://localhost:6379"
		mock_settings.RATE_LIMIT_TRUST_PROXY = False
		mock_settings.RATE_LIMIT_PROXY_COUNT = 1

		mock_limiter_instance = MagicMock()
		mock_limiter_instance.is_allowed.return_value = (True, {"remaining": 4})

		with patch("src.config.settings", mock_settings):
			with patch("src.services.rate_limiter.RateLimiter", return_value=mock_limiter_instance):
				await dep(request)

		mock_limiter_instance.is_allowed.assert_called_once()

	@pytest.mark.asyncio
	async def test_blocked_request_raises_429(self):
		"""When limiter.is_allowed returns (False, ...), HTTP 429 is raised."""
		from src.dependencies import create_rate_limit_dependency
		dep = create_rate_limit_dependency("login", 5, 1)
		request = MockRequest(client_host="10.0.0.1")

		mock_settings = MagicMock()
		mock_settings.RATE_LIMIT_ENABLED = True
		mock_settings.REDIS_URL = "redis://localhost:6379"
		mock_settings.RATE_LIMIT_TRUST_PROXY = False
		mock_settings.RATE_LIMIT_PROXY_COUNT = 1

		mock_limiter_instance = MagicMock()
		mock_limiter_instance.is_allowed.return_value = (False, {"retry_after": 60})

		with patch("src.config.settings", mock_settings):
			with patch("src.services.rate_limiter.RateLimiter", return_value=mock_limiter_instance):
				with pytest.raises(HTTPException) as exc_info:
					await dep(request)

		assert exc_info.value.status_code == 429
		assert "Retry-After" in exc_info.value.headers
