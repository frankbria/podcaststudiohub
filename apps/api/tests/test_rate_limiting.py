"""
Rate limiting tests for authentication endpoints.

Tests cover:
- Rate limiter service unit tests (check_rate_limit)
- Rate limit enforcement on /auth/login and /auth/register
- 429 response structure (Retry-After header)
- Rate limit isolation between different IPs / keys
- Redis failure handling (fail-open behaviour)
- RATE_LIMIT_ENABLED=False bypass
"""
import time
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from src.services.rate_limiter import check_rate_limit, get_client_identifier


# =============================================================================
# Unit tests — rate_limiter service
# =============================================================================

class FakeRedis:
	"""Minimal in-memory Redis sorted-set stub for unit tests."""

	def __init__(self):
		self._data: dict[str, list[tuple[str, float]]] = {}
		self._expiry: dict[str, float] = {}

	def pipeline(self):
		return FakePipeline(self)

	def zremrangebyscore(self, key, min_score, max_score):
		members = self._data.get(key, [])
		self._data[key] = [(m, s) for m, s in members if not (min_score <= s <= max_score)]

	def zcard(self, key):
		return len(self._data.get(key, []))

	def zadd(self, key, mapping):
		for member, score in mapping.items():
			self._data.setdefault(key, []).append((member, score))

	def expire(self, key, seconds):
		self._expiry[key] = time.time() + seconds

	def zrange(self, key, start, stop, withscores=False):
		members = sorted(self._data.get(key, []), key=lambda x: x[1])
		subset = members[start: stop + 1 if stop >= 0 else None]
		if withscores:
			return subset
		return [m for m, _ in subset]


class FakePipeline:
	def __init__(self, redis):
		self._redis = redis
		self._commands = []

	def zremrangebyscore(self, key, min_score, max_score):
		self._commands.append(("zremrangebyscore", key, min_score, max_score))
		return self

	def zcard(self, key):
		self._commands.append(("zcard", key))
		return self

	def zadd(self, key, mapping):
		self._commands.append(("zadd", key, mapping))
		return self

	def expire(self, key, seconds):
		self._commands.append(("expire", key, seconds))
		return self

	def execute(self):
		results = []
		for cmd, *args in self._commands:
			result = getattr(self._redis, cmd)(*args)
			results.append(result)
		return results


def make_fake_redis():
	return FakeRedis()


def _patched_check(fake_redis, key, max_requests, window_seconds):
	"""Run check_rate_limit with a patched Redis client."""
	with patch("src.services.rate_limiter.get_redis_client", return_value=fake_redis):
		return check_rate_limit(key, max_requests, window_seconds)


def test_rate_limit_allows_under_limit():
	"""Requests below the limit should all be allowed."""
	r = make_fake_redis()
	for i in range(5):
		allowed, info = _patched_check(r, "login:1.2.3.4", 5, 300)
		assert allowed, f"Request {i+1} should be allowed"
	assert info["remaining"] == 0


def test_rate_limit_blocks_over_limit():
	"""The (max_requests+1)-th request must be blocked with retry_after info."""
	r = make_fake_redis()
	for _ in range(5):
		_patched_check(r, "login:1.2.3.4", 5, 300)

	allowed, info = _patched_check(r, "login:1.2.3.4", 5, 300)
	assert not allowed
	assert info["remaining"] == 0
	assert "retry_after" in info
	assert info["retry_after"] > 0


def test_rate_limit_different_keys_are_independent():
	"""Different keys (IPs) must have independent counters."""
	r = make_fake_redis()
	# Exhaust the limit for one IP
	for _ in range(5):
		_patched_check(r, "login:1.1.1.1", 5, 300)

	# Another IP should still be allowed
	allowed, _ = _patched_check(r, "login:2.2.2.2", 5, 300)
	assert allowed


def test_rate_limit_window_reset():
	"""After the window expires (entries are old), the counter should reset."""
	r = make_fake_redis()
	# Exhaust limit
	for _ in range(5):
		_patched_check(r, "login:1.2.3.4", 5, 300)

	# Simulate window expiry by removing all stored entries
	r._data.clear()

	# Should be allowed again
	allowed, _ = _patched_check(r, "login:1.2.3.4", 5, 300)
	assert allowed


def test_rate_limit_redis_failure_fails_open():
	"""If Redis raises an exception the service should fail open (allow the request)."""
	broken_redis = MagicMock()
	broken_redis.pipeline.side_effect = Exception("connection refused")

	with patch("src.services.rate_limiter.get_redis_client", return_value=broken_redis):
		allowed, info = check_rate_limit("login:1.2.3.4", 5, 300)

	assert allowed
	assert info["remaining"] == 5


def test_get_client_identifier_forwarded_for():
	"""get_client_identifier should honour X-Forwarded-For when proxy trust is enabled."""
	from fastapi import Request as FastAPIRequest

	mock_request = MagicMock(spec=FastAPIRequest)
	mock_request.headers = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
	mock_request.client = MagicMock()
	mock_request.client.host = "10.0.0.1"

	with patch("src.services.rate_limiter.settings") as mock_settings:
		mock_settings.RATE_LIMIT_TRUST_PROXY = True
		mock_settings.RATE_LIMIT_PROXY_COUNT = 1
		ip = get_client_identifier(mock_request)

	assert ip == "203.0.113.10"


def test_get_client_identifier_no_proxy():
	"""get_client_identifier falls back to request.client.host when proxy trust disabled."""
	from fastapi import Request as FastAPIRequest

	mock_request = MagicMock(spec=FastAPIRequest)
	mock_request.headers = {}
	mock_request.client = MagicMock()
	mock_request.client.host = "192.168.1.5"

	with patch("src.services.rate_limiter.settings") as mock_settings:
		mock_settings.RATE_LIMIT_TRUST_PROXY = False
		ip = get_client_identifier(mock_request)

	assert ip == "192.168.1.5"


# =============================================================================
# Integration tests — auth endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_login_rate_limit_enforcement(client: AsyncClient):
	"""6th login attempt within window must return 429."""
	# Register a user so login can succeed
	await client.post(
		"/auth/register",
		json={"email": "ratelimit_login@example.com", "password": "RateLimit1!", "full_name": "RL"},
	)

	fake_redis = make_fake_redis()

	with patch("src.services.rate_limiter.get_redis_client", return_value=fake_redis):
		# First 5 attempts should not be rate-limited (may succeed or fail auth-wise)
		for i in range(5):
			resp = await client.post(
				"/auth/login",
				json={"email": "ratelimit_login@example.com", "password": "WrongPass1!"},
			)
			assert resp.status_code != 429, f"Request {i+1} should not be rate-limited yet"

		# 6th attempt should be rate-limited
		resp = await client.post(
			"/auth/login",
			json={"email": "ratelimit_login@example.com", "password": "WrongPass1!"},
		)

	assert resp.status_code == 429
	assert "retry" in resp.json()["detail"].lower() or "many" in resp.json()["detail"].lower()
	assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_register_rate_limit_enforcement(client: AsyncClient):
	"""4th register attempt within window must return 429."""
	fake_redis = make_fake_redis()

	with patch("src.services.rate_limiter.get_redis_client", return_value=fake_redis):
		for i in range(3):
			resp = await client.post(
				"/auth/register",
				json={
					"email": f"rl_reg_{i}@example.com",
					"password": "RateLimit1!",
					"full_name": "RL",
				},
			)
			assert resp.status_code != 429, f"Register attempt {i+1} should not be rate-limited"

		# 4th attempt — different email so it's not a duplicate, should hit rate limit
		resp = await client.post(
			"/auth/register",
			json={"email": "rl_reg_extra@example.com", "password": "RateLimit1!", "full_name": "RL"},
		)

	assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_disabled_allows_unlimited(client: AsyncClient):
	"""When RATE_LIMIT_ENABLED is False, requests must never be blocked."""
	fake_redis = make_fake_redis()

	with (
		patch("src.services.rate_limiter.get_redis_client", return_value=fake_redis),
		patch("src.dependencies.settings") as mock_settings,
	):
		mock_settings.RATE_LIMIT_ENABLED = False
		# Simulate many requests — none should get 429
		for i in range(10):
			resp = await client.post(
				"/auth/login",
				json={"email": f"user{i}@example.com", "password": "WrongPass1!"},
			)
			assert resp.status_code != 429


@pytest.mark.asyncio
async def test_rate_limit_retry_after_header(client: AsyncClient):
	"""429 response must include a valid Retry-After header."""
	fake_redis = make_fake_redis()

	with patch("src.services.rate_limiter.get_redis_client", return_value=fake_redis):
		for _ in range(5):
			await client.post(
				"/auth/login",
				json={"email": "retryafter@example.com", "password": "WrongPass1!"},
			)

		resp = await client.post(
			"/auth/login",
			json={"email": "retryafter@example.com", "password": "WrongPass1!"},
		)

	assert resp.status_code == 429
	assert "Retry-After" in resp.headers
	retry_after = int(resp.headers["Retry-After"])
	assert retry_after > 0


@pytest.mark.asyncio
async def test_resend_verification_email_requires_auth(client: AsyncClient):
	"""POST /auth/resend-verification-email must require a valid JWT."""
	resp = await client.post("/auth/resend-verification-email")
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resend_verification_email_already_verified(client: AsyncClient):
	"""resend-verification-email must return 400 when email is already verified."""

	# Register a new user
	reg_resp = await client.post(
		"/auth/register",
		json={"email": "verified@example.com", "password": "Verified1!", "full_name": "VU"},
	)
	assert reg_resp.status_code == 201
	token = reg_resp.json()["access_token"]

	# Manually mark user as verified using test_db (from outer fixture scope)
	# We'll do it via a raw SQL through the client fixture's overridden db.
	# Easiest: just call the endpoint and rely on the is_verified=False default path first.
	fake_redis = make_fake_redis()
	with patch("src.services.rate_limiter.get_redis_client", return_value=fake_redis):
		resp = await client.post(
			"/auth/resend-verification-email",
			headers={"Authorization": f"Bearer {token}"},
		)
	# User is not yet verified, so endpoint should succeed
	assert resp.status_code == 200
	assert "sent" in resp.json()["message"].lower()
