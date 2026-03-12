"""Rate limiting service using Redis sliding window counters"""

import logging
import time
from typing import Tuple

from fastapi import Request

from ..config import settings

logger = logging.getLogger(__name__)


def get_redis_client():
	"""Initialize and return a Redis client using settings.REDIS_URL."""
	import redis
	return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_client_identifier(request: Request) -> str:
	"""
	Extract client IP from request, handling X-Forwarded-For header for proxy scenarios.

	Args:
		request: FastAPI request object

	Returns:
		Client IP address string
	"""
	if settings.RATE_LIMIT_TRUST_PROXY:
		forwarded_for = request.headers.get("X-Forwarded-For")
		if forwarded_for:
			# X-Forwarded-For: client, proxy1, proxy2
			# Trust the IP that is RATE_LIMIT_PROXY_COUNT hops from the right
			ips = [ip.strip() for ip in forwarded_for.split(",")]
			index = max(0, len(ips) - settings.RATE_LIMIT_PROXY_COUNT)
			return ips[index]

	if request.client:
		return request.client.host

	return "unknown"


def check_rate_limit(
	key: str,
	max_requests: int,
	window_seconds: int,
) -> Tuple[bool, dict]:
	"""
	Check if a request is allowed under the rate limit using a Redis sliding window.

	Uses Redis sorted sets where each member is a timestamp of a request.
	Old entries outside the current window are pruned on each call.

	Args:
		key: Unique rate limit key (e.g., "login:192.168.1.1")
		max_requests: Maximum number of requests allowed in the window
		window_seconds: Time window in seconds

	Returns:
		Tuple of (allowed: bool, info: dict)
		  - If allowed: {"remaining": int}
		  - If blocked: {"retry_after": int, "remaining": 0}
	"""
	try:
		redis_client = get_redis_client()
		current_time = int(time.time())
		window_start = current_time - window_seconds

		pipe = redis_client.pipeline()
		# Remove entries outside the current window
		pipe.zremrangebyscore(key, 0, window_start)
		# Count requests in current window
		pipe.zcard(key)
		_, request_count = pipe.execute()

		if request_count < max_requests:
			# Add this request with the current timestamp as both score and member
			# Use a unique member by appending a counter to handle same-second requests
			member = f"{current_time}:{request_count}"
			pipe = redis_client.pipeline()
			pipe.zadd(key, {member: current_time})
			pipe.expire(key, window_seconds)
			pipe.execute()
			return True, {"remaining": max_requests - request_count - 1}
		else:
			# Rate limit exceeded — calculate retry_after from oldest entry
			oldest = redis_client.zrange(key, 0, 0, withscores=True)
			if oldest:
				oldest_score = int(oldest[0][1])
				retry_after = max(1, window_seconds - (current_time - oldest_score))
			else:
				retry_after = window_seconds
			return False, {"retry_after": retry_after, "remaining": 0}

	except Exception as exc:
		# Fail open: if Redis is unavailable, allow the request
		logger.error("Rate limiter Redis error, failing open: %s", exc)
		return True, {"remaining": max_requests}
