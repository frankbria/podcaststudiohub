"""
Tests for retry utilities: calculate_retry_countdown and should_retry_exception.
"""
import pytest
from unittest.mock import MagicMock


# ============================================================================
# calculate_retry_countdown tests
# ============================================================================

class TestCalculateRetryCountdown:
	"""Tests for exponential backoff countdown calculation."""

	def test_retry_count_0(self):
		"""retry_count=0 → 5 * 2^0 = 5 seconds."""
		from src.tasks.retry_utils import calculate_retry_countdown
		assert calculate_retry_countdown(0) == 5

	def test_retry_count_1(self):
		"""retry_count=1 → 5 * 2^1 = 10 seconds."""
		from src.tasks.retry_utils import calculate_retry_countdown
		assert calculate_retry_countdown(1) == 10

	def test_retry_count_2(self):
		"""retry_count=2 → 5 * 2^2 = 20 seconds."""
		from src.tasks.retry_utils import calculate_retry_countdown
		assert calculate_retry_countdown(2) == 20

	def test_retry_count_3(self):
		"""retry_count=3 → 5 * 2^3 = 40 seconds."""
		from src.tasks.retry_utils import calculate_retry_countdown
		assert calculate_retry_countdown(3) == 40

	def test_cap_at_300_seconds(self):
		"""Large retry_count is capped at 300 seconds (5 minutes)."""
		from src.tasks.retry_utils import calculate_retry_countdown
		# retry_count=6 → 5 * 64 = 320 > 300 → capped at 300
		assert calculate_retry_countdown(6) == 300

	def test_custom_base_seconds(self):
		"""Custom base_seconds parameter is respected."""
		from src.tasks.retry_utils import calculate_retry_countdown
		assert calculate_retry_countdown(0, base_seconds=10) == 10
		assert calculate_retry_countdown(1, base_seconds=10) == 20
		assert calculate_retry_countdown(2, base_seconds=10) == 40

	def test_sequence_is_exponential(self):
		"""Each retry doubles the previous countdown (up to cap)."""
		from src.tasks.retry_utils import calculate_retry_countdown
		counts = [calculate_retry_countdown(i) for i in range(4)]
		# 5, 10, 20, 40
		assert counts[1] == counts[0] * 2
		assert counts[2] == counts[1] * 2
		assert counts[3] == counts[2] * 2


# ============================================================================
# should_retry_exception tests
# ============================================================================

class TestShouldRetryException:
	"""Tests for selective retry logic."""

	# --- Permanent errors (should NOT retry) ---

	def test_value_error_not_retried(self):
		"""ValueError is a permanent/validation error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(ValueError("bad input")) is False

	def test_type_error_not_retried(self):
		"""TypeError is a programming error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(TypeError("wrong type")) is False

	def test_key_error_not_retried(self):
		"""KeyError is a programming error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(KeyError("missing key")) is False

	def test_attribute_error_not_retried(self):
		"""AttributeError is a programming error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(AttributeError("no attr")) is False

	def test_http_400_not_retried(self):
		"""HTTP 400 Bad Request is a permanent client error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=400)
		assert should_retry_exception(exc) is False

	def test_http_401_not_retried(self):
		"""HTTP 401 Unauthorized is a permanent auth error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=401)
		assert should_retry_exception(exc) is False

	def test_http_403_not_retried(self):
		"""HTTP 403 Forbidden is a permanent auth error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=403)
		assert should_retry_exception(exc) is False

	def test_http_404_not_retried(self):
		"""HTTP 404 Not Found is a permanent client error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=404)
		assert should_retry_exception(exc) is False

	def test_s3_non_retryable_client_error(self):
		"""S3 AccessDenied is a permanent error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		from botocore.exceptions import ClientError
		exc = ClientError(
			{"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
			"PutObject"
		)
		assert should_retry_exception(exc) is False

	def test_s3_no_such_bucket_not_retried(self):
		"""S3 NoSuchBucket is a permanent config error — no retry."""
		from src.tasks.retry_utils import should_retry_exception
		from botocore.exceptions import ClientError
		exc = ClientError(
			{"Error": {"Code": "NoSuchBucket", "Message": "Bucket not found"}},
			"PutObject"
		)
		assert should_retry_exception(exc) is False

	# --- Transient errors (SHOULD retry) ---

	def test_timeout_error_retried(self):
		"""Python built-in TimeoutError is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(TimeoutError("timed out")) is True

	def test_connection_error_retried(self):
		"""Python built-in ConnectionError is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(ConnectionError("connection failed")) is True

	def test_os_error_retried(self):
		"""OSError (e.g. network I/O) is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(OSError("I/O error")) is True

	def test_requests_timeout_retried(self):
		"""requests.Timeout is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		assert should_retry_exception(requests.exceptions.Timeout()) is True

	def test_requests_connection_error_retried(self):
		"""requests.ConnectionError is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		assert should_retry_exception(requests.exceptions.ConnectionError()) is True

	def test_http_429_retried(self):
		"""HTTP 429 Too Many Requests (rate limiting) is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=429)
		assert should_retry_exception(exc) is True

	def test_http_500_retried(self):
		"""HTTP 500 Internal Server Error is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=500)
		assert should_retry_exception(exc) is True

	def test_http_503_retried(self):
		"""HTTP 503 Service Unavailable is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = MagicMock(status_code=503)
		assert should_retry_exception(exc) is True

	def test_s3_service_unavailable_retried(self):
		"""S3 ServiceUnavailable is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		from botocore.exceptions import ClientError
		exc = ClientError(
			{"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
			"PutObject"
		)
		assert should_retry_exception(exc) is True

	def test_s3_slow_down_retried(self):
		"""S3 SlowDown (rate limiting) is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		from botocore.exceptions import ClientError
		exc = ClientError(
			{"Error": {"Code": "SlowDown", "Message": "Please reduce request rate"}},
			"PutObject"
		)
		assert should_retry_exception(exc) is True

	def test_s3_internal_error_retried(self):
		"""S3 InternalError is transient — retry."""
		from src.tasks.retry_utils import should_retry_exception
		from botocore.exceptions import ClientError
		exc = ClientError(
			{"Error": {"Code": "InternalError", "Message": "Internal error"}},
			"PutObject"
		)
		assert should_retry_exception(exc) is True

	def test_generic_runtime_error_retried(self):
		"""Unknown RuntimeError defaults to retry."""
		from src.tasks.retry_utils import should_retry_exception
		assert should_retry_exception(RuntimeError("unexpected failure")) is True

	def test_http_error_without_response_retried(self):
		"""HTTPError without a response object defaults to retry."""
		from src.tasks.retry_utils import should_retry_exception
		import requests
		exc = requests.exceptions.HTTPError()
		exc.response = None
		assert should_retry_exception(exc) is True
