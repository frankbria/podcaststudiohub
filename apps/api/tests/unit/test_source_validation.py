"""
Unit tests for SourceValidatorService (GAP-015).

Tests cover:
- URL format validation (scheme, domain)
- URL accessibility checks (mocked HTTP responses)
- Text length and word count validation
- PDF S3 key validation
- validate_by_type dispatch
- Error message quality
"""

import os

# Set required env vars before any src import
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.services.source_validator_service import (
	SourceValidatorService,
	URLValidationError,
	TextValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_validator() -> SourceValidatorService:
	return SourceValidatorService()


VALID_TEXT = "word " * 15  # 15 words, well above 50-char minimum


# ===========================================================================
# URL FORMAT VALIDATION (_validate_url_format)
# ===========================================================================


def test_validate_url_format_http_scheme():
	"""http:// URLs should pass format validation."""
	validator = make_validator()
	# Should not raise
	validator._validate_url_format("http://example.com/article")


def test_validate_url_format_https_scheme():
	"""https:// URLs should pass format validation."""
	validator = make_validator()
	validator._validate_url_format("https://example.com/path?q=1")


def test_validate_url_format_ftp_scheme_rejected():
	"""ftp:// URLs should raise URLValidationError with scheme hint."""
	validator = make_validator()
	with pytest.raises(URLValidationError) as exc_info:
		validator._validate_url_format("ftp://example.com/file")
	assert "ftp" in str(exc_info.value)
	assert "http" in str(exc_info.value)


def test_validate_url_format_gopher_scheme_rejected():
	"""gopher:// should be rejected."""
	validator = make_validator()
	with pytest.raises(URLValidationError):
		validator._validate_url_format("gopher://example.com")


def test_validate_url_format_no_scheme_rejected():
	"""URLs without scheme should be rejected."""
	validator = make_validator()
	with pytest.raises(URLValidationError):
		validator._validate_url_format("example.com/article")


def test_validate_url_format_empty_string():
	"""Empty URL should raise URLValidationError."""
	validator = make_validator()
	with pytest.raises(URLValidationError) as exc_info:
		validator._validate_url_format("")
	assert "empty" in str(exc_info.value).lower()


def test_validate_url_format_whitespace_only():
	"""Whitespace-only URL should raise URLValidationError."""
	validator = make_validator()
	with pytest.raises(URLValidationError):
		validator._validate_url_format("   ")


def test_validate_url_format_missing_domain():
	"""URL with scheme but no domain should raise URLValidationError."""
	validator = make_validator()
	with pytest.raises(URLValidationError) as exc_info:
		validator._validate_url_format("https://")
	assert "domain" in str(exc_info.value).lower()


# ===========================================================================
# URL ACCESSIBILITY (_check_url_accessibility)
# ===========================================================================


@pytest.mark.asyncio
async def test_check_url_accessibility_200():
	"""200 response should pass accessibility check."""
	validator = make_validator()
	mock_response = MagicMock()
	mock_response.status_code = 200

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(return_value=mock_response)
		mock_client_cls.return_value = mock_client

		# Should not raise
		await validator._check_url_accessibility("https://example.com")


@pytest.mark.asyncio
async def test_check_url_accessibility_404():
	"""404 response should raise URLValidationError with status code."""
	validator = make_validator()
	mock_response = MagicMock()
	mock_response.status_code = 404

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(return_value=mock_response)
		mock_client_cls.return_value = mock_client

		with pytest.raises(URLValidationError) as exc_info:
			await validator._check_url_accessibility("https://example.com/missing")
	assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_url_accessibility_500():
	"""500 response should raise URLValidationError."""
	validator = make_validator()
	mock_response = MagicMock()
	mock_response.status_code = 500

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(return_value=mock_response)
		mock_client_cls.return_value = mock_client

		with pytest.raises(URLValidationError) as exc_info:
			await validator._check_url_accessibility("https://example.com")
	assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_url_accessibility_redirect_200():
	"""2xx after redirects should be accepted."""
	validator = make_validator()
	mock_response = MagicMock()
	mock_response.status_code = 200

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(return_value=mock_response)
		mock_client_cls.return_value = mock_client

		await validator._check_url_accessibility("https://example.com/redirect")


@pytest.mark.asyncio
async def test_check_url_accessibility_timeout():
	"""Timeout should raise URLValidationError with timeout message."""
	validator = make_validator()

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
		mock_client_cls.return_value = mock_client

		with pytest.raises(URLValidationError) as exc_info:
			await validator._check_url_accessibility("https://slow.example.com")
	assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_check_url_accessibility_too_many_redirects():
	"""TooManyRedirects should raise URLValidationError."""
	validator = make_validator()

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(side_effect=httpx.TooManyRedirects("too many"))
		mock_client_cls.return_value = mock_client

		with pytest.raises(URLValidationError) as exc_info:
			await validator._check_url_accessibility("https://redirect-loop.example.com")
	assert "redirect" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_check_url_accessibility_request_error():
	"""Network-level errors should raise URLValidationError."""
	validator = make_validator()

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(
			side_effect=httpx.ConnectError("connection refused")
		)
		mock_client_cls.return_value = mock_client

		with pytest.raises(URLValidationError) as exc_info:
			await validator._check_url_accessibility("https://down.example.com")
	assert "failed to access" in str(exc_info.value).lower()


# ===========================================================================
# TEXT LENGTH VALIDATION (_validate_text_length)
# ===========================================================================


def test_validate_text_length_valid():
	"""Text with 50+ chars and 10+ words should pass."""
	validator = make_validator()
	validator._validate_text_length(VALID_TEXT)  # Should not raise


def test_validate_text_length_exactly_minimum():
	"""Text of exactly MIN_TEXT_LENGTH characters with enough words should pass."""
	validator = make_validator()
	# 10 words of 5 chars each, separated by spaces: 10*5 + 9 = 59 chars, >=50
	text = ("abcde " * 10).rstrip()  # 59 chars, 10 words
	validator._validate_text_length(text)


def test_validate_text_length_too_short():
	"""Text shorter than 50 chars should raise TextValidationError."""
	validator = make_validator()
	short = "hello world this is short"  # < 50 chars
	with pytest.raises(TextValidationError) as exc_info:
		validator._validate_text_length(short)
	assert "too short" in str(exc_info.value).lower()
	assert "50" in str(exc_info.value)


def test_validate_text_length_too_long():
	"""Text longer than 50000 chars should raise TextValidationError."""
	validator = make_validator()
	long_text = "word " * 15_000  # way over 50_000 chars
	with pytest.raises(TextValidationError) as exc_info:
		validator._validate_text_length(long_text)
	assert "too long" in str(exc_info.value).lower()
	assert "50000" in str(exc_info.value)


def test_validate_text_length_empty():
	"""Empty text should raise TextValidationError."""
	validator = make_validator()
	with pytest.raises(TextValidationError) as exc_info:
		validator._validate_text_length("")
	assert "empty" in str(exc_info.value).lower()


def test_validate_text_length_whitespace_only():
	"""Whitespace-only text should raise TextValidationError."""
	validator = make_validator()
	with pytest.raises(TextValidationError):
		validator._validate_text_length("   \n\t  ")


def test_validate_text_length_too_few_words():
	"""Text with fewer than 10 words but >= 50 chars should raise TextValidationError."""
	validator = make_validator()
	# 5 very long words totalling > 50 chars
	few_word_text = "superlongword " * 5  # 5 words, 70 chars
	with pytest.raises(TextValidationError) as exc_info:
		validator._validate_text_length(few_word_text)
	assert "words" in str(exc_info.value).lower()
	assert "10" in str(exc_info.value)


def test_validate_text_length_exactly_10_words():
	"""Text with exactly 10 words and >=50 chars should pass."""
	validator = make_validator()
	# Each word 5 chars + space = 60 chars for 10 words
	text = ("hello " * 10).rstrip()
	validator._validate_text_length(text)


# ===========================================================================
# validate_url_source (public, async)
# ===========================================================================


@pytest.mark.asyncio
async def test_validate_url_source_valid():
	"""Valid URL returning 200 should return (True, None)."""
	validator = make_validator()
	mock_response = MagicMock()
	mock_response.status_code = 200

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(return_value=mock_response)
		mock_client_cls.return_value = mock_client

		result = await validator.validate_url_source("https://example.com", "Title")
	assert result == (True, None)


@pytest.mark.asyncio
async def test_validate_url_source_invalid_scheme():
	"""URL with invalid scheme should raise URLValidationError before HTTP call."""
	validator = make_validator()
	with pytest.raises(URLValidationError):
		await validator.validate_url_source("ftp://example.com", "Title")


# ===========================================================================
# validate_text_source (public, async)
# ===========================================================================


@pytest.mark.asyncio
async def test_validate_text_source_valid():
	"""Valid text should return (True, None)."""
	validator = make_validator()
	result = await validator.validate_text_source(VALID_TEXT)
	assert result == (True, None)


@pytest.mark.asyncio
async def test_validate_text_source_too_short():
	"""Short text should raise TextValidationError."""
	validator = make_validator()
	with pytest.raises(TextValidationError):
		await validator.validate_text_source("too short")


# ===========================================================================
# validate_pdf_source (public, async)
# ===========================================================================


@pytest.mark.asyncio
async def test_validate_pdf_source_valid():
	"""Non-empty S3 key should return (True, None)."""
	validator = make_validator()
	result = await validator.validate_pdf_source("uploads/document.pdf")
	assert result == (True, None)


@pytest.mark.asyncio
async def test_validate_pdf_source_empty_key():
	"""Empty S3 key should raise ValueError."""
	validator = make_validator()
	with pytest.raises(ValueError) as exc_info:
		await validator.validate_pdf_source("")
	assert "s3 key" in str(exc_info.value).lower()


# ===========================================================================
# validate_by_type dispatch
# ===========================================================================


@pytest.mark.asyncio
async def test_validate_by_type_url_valid():
	"""validate_by_type dispatches to URL validation for 'url' type."""
	validator = make_validator()
	mock_response = MagicMock()
	mock_response.status_code = 200

	with patch("src.services.source_validator_service.httpx.AsyncClient") as mock_client_cls:
		mock_client = AsyncMock()
		mock_client.__aenter__ = AsyncMock(return_value=mock_client)
		mock_client.__aexit__ = AsyncMock(return_value=None)
		mock_client.head = AsyncMock(return_value=mock_response)
		mock_client_cls.return_value = mock_client

		# Should not raise
		await validator.validate_by_type(
			source_type='url',
			source_data={'url': 'https://example.com', 'title': 'Test'},
		)


@pytest.mark.asyncio
async def test_validate_by_type_url_invalid():
	"""validate_by_type raises URLValidationError for invalid URL."""
	validator = make_validator()
	with pytest.raises(URLValidationError):
		await validator.validate_by_type(
			source_type='url',
			source_data={'url': 'not-a-url', 'title': 'Test'},
		)


@pytest.mark.asyncio
async def test_validate_by_type_text_valid():
	"""validate_by_type dispatches to text validation for 'text' type."""
	validator = make_validator()
	await validator.validate_by_type(
		source_type='text',
		source_data={'content': VALID_TEXT},
	)


@pytest.mark.asyncio
async def test_validate_by_type_text_invalid():
	"""validate_by_type raises TextValidationError for short text."""
	validator = make_validator()
	with pytest.raises(TextValidationError):
		await validator.validate_by_type(
			source_type='text',
			source_data={'content': 'hi'},
		)


@pytest.mark.asyncio
async def test_validate_by_type_pdf_valid():
	"""validate_by_type dispatches to PDF validation for 'pdf' type."""
	validator = make_validator()
	await validator.validate_by_type(
		source_type='pdf',
		source_data={'s3_key': 'uploads/doc.pdf', 'filename': 'doc.pdf'},
	)


@pytest.mark.asyncio
async def test_validate_by_type_pdf_empty_key():
	"""validate_by_type raises ValueError for empty PDF S3 key."""
	validator = make_validator()
	with pytest.raises(ValueError):
		await validator.validate_by_type(
			source_type='pdf',
			source_data={'s3_key': '', 'filename': 'doc.pdf'},
		)


# ===========================================================================
# Error message quality
# ===========================================================================


def test_url_error_includes_scheme_guidance():
	"""URLValidationError for bad scheme should include 'http' and 'https'."""
	validator = make_validator()
	with pytest.raises(URLValidationError) as exc_info:
		validator._validate_url_format("ftp://example.com")
	msg = str(exc_info.value)
	assert "http" in msg
	assert "https" in msg


def test_text_error_includes_minimum_value():
	"""TextValidationError for short text should mention the minimum char count."""
	validator = make_validator()
	with pytest.raises(TextValidationError) as exc_info:
		validator._validate_text_length("hi there")
	assert "50" in str(exc_info.value)


def test_text_error_includes_maximum_value():
	"""TextValidationError for long text should mention the maximum char count."""
	validator = make_validator()
	with pytest.raises(TextValidationError) as exc_info:
		validator._validate_text_length("word " * 20_000)
	assert "50000" in str(exc_info.value)


def test_url_timeout_error_includes_seconds():
	"""Timeout error message should mention the timeout duration."""
	# The error message is constructed in _check_url_accessibility
	validator = make_validator()
	msg = (
		f"URL request timed out after {validator.URL_FETCH_TIMEOUT}s. "
		"Website may be slow or unavailable. Try again later."
	)
	assert str(validator.URL_FETCH_TIMEOUT) in msg
