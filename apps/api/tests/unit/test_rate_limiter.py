"""
Unit tests for the rate limiting service.

All Redis interactions are mocked so no real Redis server is required.
"""
import os

# Ensure required env vars are set before any src imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import time
from unittest.mock import MagicMock, patch

from src.services.rate_limiter import RateLimiter, get_client_ip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis_mock(card_return: int = 0, zrange_return=None):
	"""Return a MagicMock that satisfies RateLimiter's Redis usage."""
	redis_mock = MagicMock()
	pipe_mock = MagicMock()

	# pipeline().__enter__ / pipeline() both return the pipe mock
	redis_mock.pipeline.return_value = pipe_mock
	pipe_mock.execute.return_value = [None, card_return]  # [zremrangebyscore, zcard]

	if zrange_return is None:
		# Default: one entry at current time
		zrange_return = [("ts", float(int(time.time())))]
	redis_mock.zrange.return_value = zrange_return

	return redis_mock


def _make_limiter(redis_mock) -> RateLimiter:
	"""Build a RateLimiter whose internal Redis is replaced by *redis_mock*."""
	with patch("src.services.rate_limiter.Redis") as MockRedis:
		MockRedis.from_url.return_value = redis_mock
		limiter = RateLimiter("redis://localhost:6379/0")
	return limiter


# ---------------------------------------------------------------------------
# RateLimiter.is_allowed
# ---------------------------------------------------------------------------

class TestRateLimiterIsAllowed:

	def test_allows_request_under_limit(self):
		"""First request (count=0) against max=5 should be allowed."""
		redis_mock = _make_redis_mock(card_return=0)
		limiter = _make_limiter(redis_mock)

		allowed, info = limiter.is_allowed("login:1.2.3.4", max_requests=5, window_seconds=300)

		assert allowed is True
		assert info["remaining"] == 4

	def test_allows_request_at_limit_boundary(self):
		"""4th request against max=5 should still be allowed (count=4 < 5)."""
		redis_mock = _make_redis_mock(card_return=4)
		limiter = _make_limiter(redis_mock)

		allowed, info = limiter.is_allowed("login:1.2.3.4", max_requests=5, window_seconds=300)

		assert allowed is True
		assert info["remaining"] == 0

	def test_blocks_request_over_limit(self):
		"""5th request against max=5 should be blocked (count=5 >= 5)."""
		now = int(time.time())
		redis_mock = _make_redis_mock(
			card_return=5,
			zrange_return=[("ts", float(now - 10))],
		)
		limiter = _make_limiter(redis_mock)

		allowed, info = limiter.is_allowed("login:1.2.3.4", max_requests=5, window_seconds=300)

		assert allowed is False
		assert info["remaining"] == 0
		assert "retry_after" in info
		assert info["retry_after"] > 0

	def test_retry_after_value_is_positive(self):
		"""retry_after must always be >= 1."""
		now = int(time.time())
		# Oldest entry is almost at the window boundary (only 1 second ago)
		redis_mock = _make_redis_mock(
			card_return=5,
			zrange_return=[("ts", float(now - 1))],
		)
		limiter = _make_limiter(redis_mock)

		allowed, info = limiter.is_allowed("login:1.2.3.4", max_requests=5, window_seconds=300)

		assert allowed is False
		assert info["retry_after"] >= 1

	def test_different_keys_are_independent(self):
		"""Two different IP keys should not share counters."""
		redis_mock_a = _make_redis_mock(card_return=0)
		limiter_a = _make_limiter(redis_mock_a)

		redis_mock_b = _make_redis_mock(card_return=5, zrange_return=[("ts", float(int(time.time())))])
		limiter_b = _make_limiter(redis_mock_b)

		allowed_a, _ = limiter_a.is_allowed("login:1.1.1.1", max_requests=5, window_seconds=300)
		allowed_b, _ = limiter_b.is_allowed("login:2.2.2.2", max_requests=5, window_seconds=300)

		assert allowed_a is True
		assert allowed_b is False

	def test_fails_open_on_redis_exception(self):
		"""When Redis raises an exception the limiter should allow the request."""
		redis_mock = MagicMock()
		redis_mock.pipeline.side_effect = Exception("connection refused")
		limiter = _make_limiter(redis_mock)

		allowed, info = limiter.is_allowed("login:1.2.3.4", max_requests=5, window_seconds=300)

		assert allowed is True

	def test_records_request_when_allowed(self):
		"""A successful check should call zadd and expire to record the request."""
		redis_mock = _make_redis_mock(card_return=0)
		limiter = _make_limiter(redis_mock)

		limiter.is_allowed("login:1.2.3.4", max_requests=5, window_seconds=300)

		redis_mock.zadd.assert_called_once()
		redis_mock.expire.assert_called_once()


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------

class TestGetClientIp:

	def test_direct_client_no_forwarded_for(self):
		"""Without X-Forwarded-For the direct host is returned."""
		result = get_client_ip(
			client_host="10.0.0.1",
			forwarded_for=None,
			trust_proxy=True,
			proxy_count=1,
		)
		assert result == "10.0.0.1"

	def test_proxy_disabled_ignores_forwarded_for(self):
		"""When trust_proxy=False the X-Forwarded-For header is ignored."""
		result = get_client_ip(
			client_host="10.0.0.1",
			forwarded_for="5.5.5.5, 10.0.0.1",
			trust_proxy=False,
			proxy_count=1,
		)
		assert result == "10.0.0.1"

	def test_single_proxy_strips_rightmost(self):
		"""With proxy_count=1, the last entry (proxy) is stripped."""
		result = get_client_ip(
			client_host="10.0.0.1",
			forwarded_for="5.5.5.5, 10.0.0.1",
			trust_proxy=True,
			proxy_count=1,
		)
		assert result == "5.5.5.5"

	def test_two_proxies_strips_two_rightmost(self):
		"""With proxy_count=2, the two rightmost entries are stripped."""
		result = get_client_ip(
			client_host="10.0.0.1",
			forwarded_for="1.1.1.1, 2.2.2.2, 3.3.3.3",
			trust_proxy=True,
			proxy_count=2,
		)
		assert result == "1.1.1.1"

	def test_proxy_count_exceeds_list_returns_first(self):
		"""proxy_count larger than the list safely returns index 0."""
		result = get_client_ip(
			client_host="10.0.0.1",
			forwarded_for="1.1.1.1",
			trust_proxy=True,
			proxy_count=5,
		)
		assert result == "1.1.1.1"

	def test_no_client_host_returns_unknown(self):
		"""When both client_host and forwarded_for are None, return 'unknown'."""
		result = get_client_ip(
			client_host=None,
			forwarded_for=None,
			trust_proxy=True,
			proxy_count=1,
		)
		assert result == "unknown"

	def test_whitespace_trimmed_from_forwarded_for(self):
		"""IP addresses with surrounding whitespace are trimmed correctly."""
		result = get_client_ip(
			client_host="10.0.0.1",
			forwarded_for="  9.9.9.9 , 10.0.0.1 ",
			trust_proxy=True,
			proxy_count=1,
		)
		assert result == "9.9.9.9"
