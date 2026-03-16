"""
Shared retry utilities for Celery tasks.

Provides:
- calculate_backoff(): exponential backoff formula (5s, 10s, 20s)
- should_retry_exception(): selective retry decision for platform distribution
"""
import logging

logger = logging.getLogger(__name__)


def calculate_backoff(retry_count: int, base: int = 5) -> int:
	"""
	Calculate exponential backoff countdown in seconds.

	Formula: base * 2^retry_count, capped at 300 seconds (5 minutes).

	Args:
		retry_count: 0-indexed retry attempt (self.request.retries)
		base: Base delay in seconds (default: 5)

	Returns:
		Seconds to wait before the next retry attempt.

	Examples:
		retry_count=0 (first retry):  5s
		retry_count=1 (second retry): 10s
		retry_count=2 (third retry):  20s
	"""
	backoff = base * (2 ** retry_count)
	return min(backoff, 300)


def should_retry_exception(exc: Exception) -> bool:
	"""
	Determine whether an exception warrants a retry.

	Retry on transient errors:
	- Network/connection errors
	- Timeout errors
	- HTTP 5xx server errors
	- HTTP 429 rate limiting

	Do NOT retry on permanent errors:
	- ValueError, KeyError, TypeError (validation/programming errors)
	- HTTP 4xx client errors (except 429)
	- Authentication errors

	Args:
		exc: The exception to evaluate.

	Returns:
		True if the task should be retried, False otherwise.
	"""
	# Permanent errors — never retry
	if isinstance(exc, (ValueError, KeyError, TypeError, AttributeError)):
		return False

	# requests HTTP errors — check BEFORE OSError since HTTPError inherits from IOError/OSError
	try:
		import requests
		if isinstance(exc, requests.exceptions.HTTPError):
			response = getattr(exc, 'response', None)
			if response is not None:
				status_code = response.status_code
				# Retry 5xx and rate limiting (429), never 4xx (except 429)
				return status_code >= 500 or status_code == 429
			# No response attached — treat as transient
			return True
		if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
			return True
	except ImportError:
		pass

	# Transient infrastructure errors — always retry
	if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
		return True

	# Default: retry unknown exceptions rather than fail permanently
	return True
