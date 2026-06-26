"""
Unit tests for Redis-backed OAuth CSRF state (issue #273).

Redis is mocked so no real server is required, mirroring test_rate_limiter.py.
The state store must be:
- multi-instance safe (Redis-backed, not a module dict)
- one-time use (validate consumes the state atomically via GETDEL)
- fail-closed (a Redis error during validation rejects, returns None)
"""
import os

# Ensure required env vars are set before any src imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from unittest.mock import MagicMock, patch

from src.services import distribution_target_service as svc


def _patch_redis(redis_mock):
	"""Patch the module's Redis so _redis() returns redis_mock."""
	return patch.object(svc, "Redis", **{"from_url.return_value": redis_mock})


class FakeRedis:
	"""Minimal in-memory Redis double supporting setex + getdel."""

	def __init__(self):
		self.store = {}

	def setex(self, key, ttl, value):
		self.store[key] = value

	def getdel(self, key):
		return self.store.pop(key, None)


def test_generate_returns_token_and_stores_in_redis():
	fake = FakeRedis()
	with _patch_redis(fake):
		state = svc.generate_oauth_state("user-123")

	assert isinstance(state, str) and len(state) > 20
	assert fake.store[f"oauth_state:{state}"] == "user-123"


def test_generate_sets_ttl():
	redis_mock = MagicMock()
	with _patch_redis(redis_mock):
		state = svc.generate_oauth_state("user-123")

	redis_mock.setex.assert_called_once_with(
		f"oauth_state:{state}", svc._STATE_TTL_SECONDS, "user-123"
	)


def test_validate_happy_path_returns_user_id():
	fake = FakeRedis()
	with _patch_redis(fake):
		state = svc.generate_oauth_state("user-123")
		assert svc.validate_oauth_state(state) == "user-123"


def test_validate_missing_or_expired_returns_none():
	fake = FakeRedis()  # empty: expired keys are gone (Redis TTL)
	with _patch_redis(fake):
		assert svc.validate_oauth_state("never-issued") is None


def test_validate_replay_second_attempt_returns_none():
	fake = FakeRedis()
	with _patch_redis(fake):
		state = svc.generate_oauth_state("user-123")
		assert svc.validate_oauth_state(state) == "user-123"
		# Replay: one-time use means the second validation fails
		assert svc.validate_oauth_state(state) is None


def test_validate_fails_closed_on_redis_error():
	redis_mock = MagicMock()
	redis_mock.getdel.side_effect = RuntimeError("redis down")
	with _patch_redis(redis_mock):
		assert svc.validate_oauth_state("anything") is None
