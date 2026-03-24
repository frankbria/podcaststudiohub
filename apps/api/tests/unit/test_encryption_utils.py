"""
Unit tests for encryption utilities.

The DB-dependent functions (encrypt_credential, decrypt_credential, etc.)
require a live PostgreSQL + pgcrypto and are covered by integration tests.

This module covers the pure-Python helpers that can run without a database:
- is_sensitive_header: case-insensitive pattern matching for header sensitivity
"""

from src.utils.encryption import is_sensitive_header, SENSITIVE_HEADER_PATTERNS


# ===========================================================================
# is_sensitive_header
# ===========================================================================


def test_authorization_is_sensitive():
	assert is_sensitive_header("Authorization") is True


def test_authorization_lowercase_is_sensitive():
	assert is_sensitive_header("authorization") is True


def test_api_key_hyphen_is_sensitive():
	assert is_sensitive_header("api-key") is True


def test_api_key_underscore_is_sensitive():
	assert is_sensitive_header("api_key") is True


def test_x_api_key_is_sensitive():
	assert is_sensitive_header("x-api-key") is True


def test_secret_prefix_is_sensitive():
	assert is_sensitive_header("X-Secret-Token") is True


def test_token_suffix_is_sensitive():
	assert is_sensitive_header("X-Auth-Token") is True


def test_bearer_token_header_is_sensitive():
	assert is_sensitive_header("Bearer-Token") is True


def test_content_type_is_not_sensitive():
	assert is_sensitive_header("Content-Type") is False


def test_accept_is_not_sensitive():
	assert is_sensitive_header("Accept") is False


def test_user_agent_is_not_sensitive():
	assert is_sensitive_header("User-Agent") is False


def test_sensitive_header_patterns_is_frozenset():
	assert isinstance(SENSITIVE_HEADER_PATTERNS, frozenset)
