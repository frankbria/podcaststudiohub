"""
Rate limiting service using Redis sorted sets (sliding window algorithm).

Provides IP-based rate limiting for authentication endpoints.
Fails open on Redis errors to preserve availability.
"""
import logging
import time
from typing import Optional, Tuple

from redis import Redis

logger = logging.getLogger(__name__)


class RateLimiter:
	"""
	Sliding window rate limiter backed by Redis sorted sets.

	Each key maps to a sorted set where members are timestamps.
	Old entries outside the window are pruned on every check.
	"""

	def __init__(self, redis_url: str) -> None:
		"""
		Initialize rate limiter with a Redis connection.

		Args:
			redis_url: Redis connection URL (e.g. redis://localhost:6379/0)
		"""
		self._redis = Redis.from_url(redis_url, decode_responses=True)

	def is_allowed(
		self,
		key: str,
		max_requests: int,
		window_seconds: int,
	) -> Tuple[bool, dict]:
		"""
		Check whether a request identified by *key* is within the rate limit.

		Uses a Redis sorted set as a sliding window: scores are Unix timestamps
		so old entries can be pruned with ``zremrangebyscore``.

		Args:
			key: Unique identifier for the counter (e.g. ``"login:1.2.3.4"``).
			max_requests: Maximum requests allowed within the window.
			window_seconds: Length of the sliding window in seconds.

		Returns:
			A tuple ``(allowed, info)`` where *allowed* is ``True`` when the
			request should proceed and *info* is a dict containing:
			- ``remaining``: requests remaining in the current window
			- ``retry_after``: seconds until the oldest request expires
			  (only present when *allowed* is ``False``)
		"""
		try:
			current_time = int(time.time())
			window_start = current_time - window_seconds

			pipe = self._redis.pipeline()
			# Remove expired entries
			pipe.zremrangebyscore(key, 0, window_start)
			# Count remaining entries
			pipe.zcard(key)
			_, request_count = pipe.execute()

			if request_count < max_requests:
				# Record this request
				self._redis.zadd(key, {str(current_time): current_time})
				self._redis.expire(key, window_seconds)
				remaining = max_requests - request_count - 1
				return True, {"remaining": remaining}
			else:
				# Determine how long until the oldest entry expires
				oldest_entries = self._redis.zrange(key, 0, 0, withscores=True)
				if oldest_entries:
					oldest_score = int(oldest_entries[0][1])
					retry_after = max(1, window_seconds - (current_time - oldest_score))
				else:
					retry_after = window_seconds
				return False, {"remaining": 0, "retry_after": retry_after}

		except Exception as exc:
			# Fail open: log the error but allow the request
			logger.warning("Rate limiter Redis error (failing open): %s", exc)
			return True, {"remaining": -1}


def get_client_ip(
	client_host: Optional[str],
	forwarded_for: Optional[str],
	trust_proxy: bool,
	proxy_count: int,
) -> str:
	"""
	Determine the real client IP address.

	When *trust_proxy* is ``True`` and an ``X-Forwarded-For`` header is
	present, this function strips the rightmost *proxy_count* entries
	(which are the trusted reverse proxy addresses) and returns the last
	untrusted address.

	Args:
		client_host: Direct TCP peer IP (``request.client.host``).
		forwarded_for: Value of the ``X-Forwarded-For`` header, or ``None``.
		trust_proxy: Whether to honour the ``X-Forwarded-For`` header.
		proxy_count: Number of trusted proxies to strip from the right.

	Returns:
		The resolved client IP string, defaulting to ``"unknown"`` if
		nothing useful is available.
	"""
	if trust_proxy and forwarded_for:
		ips = [ip.strip() for ip in forwarded_for.split(",")]
		# Strip the rightmost *proxy_count* entries (trusted proxies)
		index = max(0, len(ips) - 1 - proxy_count)
		return ips[index]
	return client_host or "unknown"
