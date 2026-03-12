"""
Retry utilities for Celery tasks.

Provides exponential backoff calculation and selective retry logic
for transient vs permanent failures.
"""
import logging

logger = logging.getLogger(__name__)


def calculate_retry_countdown(retry_count: int, base_seconds: int = 5) -> int:
	"""
	Calculate exponential backoff countdown for task retries.

	Formula: base_seconds * 2^retry_count, capped at 5 minutes.

	Args:
		retry_count: Current retry attempt (0-indexed, i.e. self.request.retries)
		base_seconds: Base delay in seconds (default: 5)

	Returns:
		Seconds to wait before the next retry attempt

	Examples:
		retry_count=0 → 5s
		retry_count=1 → 10s
		retry_count=2 → 20s
	"""
	backoff = base_seconds * (2 ** retry_count)
	return min(backoff, 300)  # Cap at 5 minutes


def should_retry_exception(exception: Exception) -> bool:
	"""
	Determine whether an exception should trigger a Celery task retry.

	Retries on transient errors:
	- Network timeouts and connection errors
	- HTTP 5xx server errors
	- HTTP 429 rate limiting
	- boto3/S3 service-level transient errors

	Does NOT retry on permanent errors:
	- ValueError, TypeError, KeyError (programming / validation errors)
	- HTTP 4xx client errors (except 429)
	- S3 authentication / bucket-not-found errors

	Args:
		exception: The exception that was raised

	Returns:
		True if the task should be retried, False for permanent failures
	"""
	# Permanent: validation and programming errors
	if isinstance(exception, (ValueError, TypeError, KeyError, AttributeError)):
		return False

	# Requests library exceptions — check BEFORE generic OSError since
	# requests.exceptions.HTTPError is a subclass of OSError (via IOError).
	try:
		import requests
		if isinstance(exception, requests.exceptions.HTTPError):
			if hasattr(exception, 'response') and exception.response is not None:
				status_code = exception.response.status_code
				# Retry 5xx (server errors) and 429 (rate limiting); not other 4xx
				return status_code >= 500 or status_code == 429
			# Unknown HTTP error — retry conservatively
			return True
		if isinstance(exception, requests.exceptions.Timeout):
			return True
		if isinstance(exception, requests.exceptions.ConnectionError):
			return True
	except ImportError:
		pass

	# Transient: standard Python network errors
	if isinstance(exception, (TimeoutError, ConnectionError, OSError)):
		return True

	# boto3 / botocore S3 errors
	try:
		from botocore.exceptions import ClientError
		if isinstance(exception, ClientError):
			error_code = exception.response.get('Error', {}).get('Code', '')
			RETRYABLE_S3_CODES = frozenset({
				'ServiceUnavailable',
				'SlowDown',
				'RequestLimitExceeded',
				'InternalError',
				'RequestTimeout',
			})
			return error_code in RETRYABLE_S3_CODES
	except ImportError:
		pass

	# Default: retry unknown/unexpected exceptions
	return True
