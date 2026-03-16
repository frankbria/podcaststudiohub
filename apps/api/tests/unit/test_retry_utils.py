"""
Unit tests for retry utility functions.

Tests cover:
- calculate_backoff: exponential formula and cap
- should_retry_exception: selective retry decisions
"""

import pytest

from src.tasks.retry_utils import calculate_backoff, should_retry_exception


# ============================================================================
# calculate_backoff tests
# ============================================================================


class TestCalculateBackoff:

	def test_first_retry_returns_base_delay(self):
		"""retry_count=0 (first retry) returns the base delay."""
		assert calculate_backoff(0) == 5

	def test_second_retry_doubles(self):
		"""retry_count=1 (second retry) returns 2x the base delay."""
		assert calculate_backoff(1) == 10

	def test_third_retry_quadruples(self):
		"""retry_count=2 (third retry) returns 4x the base delay."""
		assert calculate_backoff(2) == 20

	def test_capped_at_300_seconds(self):
		"""Very high retry counts are capped at 300 seconds."""
		assert calculate_backoff(20) == 300

	def test_custom_base(self):
		"""Custom base delay is respected."""
		assert calculate_backoff(0, base=10) == 10
		assert calculate_backoff(1, base=10) == 20
		assert calculate_backoff(2, base=10) == 40

	def test_backoff_is_strictly_increasing(self):
		"""Each retry has a longer backoff than the previous."""
		delays = [calculate_backoff(i) for i in range(5)]
		for i in range(1, len(delays)):
			assert delays[i] >= delays[i - 1]


# ============================================================================
# should_retry_exception tests
# ============================================================================


class TestShouldRetryException:

	def test_connection_error_is_retryable(self):
		"""ConnectionError is a transient failure — retry."""
		assert should_retry_exception(ConnectionError("Connection refused")) is True

	def test_timeout_error_is_retryable(self):
		"""TimeoutError is a transient failure — retry."""
		assert should_retry_exception(TimeoutError("Request timed out")) is True

	def test_os_error_is_retryable(self):
		"""OSError is a transient failure — retry."""
		assert should_retry_exception(OSError("Broken pipe")) is True

	def test_value_error_is_not_retryable(self):
		"""ValueError is a permanent validation error — don't retry."""
		assert should_retry_exception(ValueError("Invalid input")) is False

	def test_key_error_is_not_retryable(self):
		"""KeyError is a permanent programming error — don't retry."""
		assert should_retry_exception(KeyError("missing_field")) is False

	def test_type_error_is_not_retryable(self):
		"""TypeError is a permanent programming error — don't retry."""
		assert should_retry_exception(TypeError("wrong type")) is False

	def test_attribute_error_is_not_retryable(self):
		"""AttributeError is a permanent programming error — don't retry."""
		assert should_retry_exception(AttributeError("no such attr")) is False

	def test_generic_exception_defaults_to_retryable(self):
		"""Unknown exceptions default to retryable (better to retry than lose the job)."""
		assert should_retry_exception(RuntimeError("Unexpected failure")) is True

	def test_http_500_is_retryable(self):
		"""HTTP 5xx server errors are transient — retry."""
		try:
			import requests
			exc = requests.exceptions.HTTPError(response=_make_http_response(500))
			assert should_retry_exception(exc) is True
		except ImportError:
			pytest.skip("requests not available")

	def test_http_429_is_retryable(self):
		"""HTTP 429 rate limiting is transient — retry."""
		try:
			import requests
			exc = requests.exceptions.HTTPError(response=_make_http_response(429))
			assert should_retry_exception(exc) is True
		except ImportError:
			pytest.skip("requests not available")

	def test_http_400_is_not_retryable(self):
		"""HTTP 400 client errors are permanent — don't retry."""
		try:
			import requests
			exc = requests.exceptions.HTTPError(response=_make_http_response(400))
			assert should_retry_exception(exc) is False
		except ImportError:
			pytest.skip("requests not available")

	def test_http_404_is_not_retryable(self):
		"""HTTP 404 not found is permanent — don't retry."""
		try:
			import requests
			exc = requests.exceptions.HTTPError(response=_make_http_response(404))
			assert should_retry_exception(exc) is False
		except ImportError:
			pytest.skip("requests not available")

	def test_requests_connection_error_is_retryable(self):
		"""requests.ConnectionError is a transient failure — retry."""
		try:
			import requests
			exc = requests.exceptions.ConnectionError("Network unreachable")
			assert should_retry_exception(exc) is True
		except ImportError:
			pytest.skip("requests not available")

	def test_requests_timeout_is_retryable(self):
		"""requests.Timeout is a transient failure — retry."""
		try:
			import requests
			exc = requests.exceptions.Timeout("Request timed out")
			assert should_retry_exception(exc) is True
		except ImportError:
			pytest.skip("requests not available")


# ============================================================================
# Helpers
# ============================================================================


def _make_http_response(status_code: int):
	"""Create a minimal mock HTTP response for requests exceptions."""
	from unittest.mock import MagicMock
	response = MagicMock()
	response.status_code = status_code
	return response
