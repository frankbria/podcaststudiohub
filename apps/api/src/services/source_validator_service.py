"""
Source data validation service for content creation.

Validates URL format and accessibility, text length constraints, and PDF source
keys before content sources are persisted. Implements GAP-015.
"""

import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class SourceValidationError(Exception):
	"""Base exception for source validation failures."""
	pass


class URLValidationError(SourceValidationError):
	"""URL validation failed."""
	pass


class TextValidationError(SourceValidationError):
	"""Text validation failed."""
	pass


class SourceValidatorService:
	"""Validate content source data before storage."""

	# Configuration constants
	MIN_TEXT_LENGTH = 50
	MAX_TEXT_LENGTH = 50_000
	URL_FETCH_TIMEOUT = 10  # seconds
	MAX_REDIRECT_HOPS = 3
	MIN_WORDS_FOR_PODCAST = 10
	ALLOWED_SCHEMES = ('http', 'https')

	def _validate_url_format(self, url: str) -> None:
		"""
		Validate URL has a valid format (http/https scheme and non-empty domain).

		Args:
			url: URL string to validate

		Raises:
			URLValidationError: If format is invalid
		"""
		if not url or not url.strip():
			raise URLValidationError("URL cannot be empty")

		try:
			parsed = urlparse(url)
		except Exception as exc:
			raise URLValidationError(f"Invalid URL format: {exc}") from exc

		if parsed.scheme not in self.ALLOWED_SCHEMES:
			raise URLValidationError(
				f"Invalid URL scheme: '{parsed.scheme}'. "
				f"Must be 'http' or 'https'. "
				f"Example: https://example.com/article"
			)

		if not parsed.netloc:
			raise URLValidationError(
				"Invalid URL: missing domain. "
				"Example: https://example.com/article"
			)

	async def _check_url_accessibility(self, url: str) -> None:
		"""
		Issue a HEAD request to verify the URL is publicly reachable.

		Args:
			url: URL to check

		Raises:
			URLValidationError: If the URL is not accessible
		"""
		try:
			async with httpx.AsyncClient(
				timeout=self.URL_FETCH_TIMEOUT,
				follow_redirects=True,
				max_redirects=self.MAX_REDIRECT_HOPS,
			) as client:
				response = await client.head(url)

			if not (200 <= response.status_code < 300):
				raise URLValidationError(
					f"URL returned HTTP {response.status_code}. "
					f"Expected 2xx success response. "
					f"Is the URL correct and publicly accessible?"
				)

		except URLValidationError:
			raise

		except httpx.TimeoutException:
			raise URLValidationError(
				f"URL request timed out after {self.URL_FETCH_TIMEOUT}s. "
				f"Website may be slow or unavailable. Try again later."
			)

		except httpx.TooManyRedirects:
			raise URLValidationError(
				f"URL has too many redirects (max {self.MAX_REDIRECT_HOPS}). "
				f"Check that the URL is correct and does not have redirect loops."
			)

		except httpx.RequestError as exc:
			raise URLValidationError(
				f"Failed to access URL: {type(exc).__name__}. "
				f"Website may be down or blocked. Is it publicly accessible?"
			) from exc

	def _validate_text_length(self, content: str) -> None:
		"""
		Validate text content length and word count.

		Args:
			content: Text content to validate

		Raises:
			TextValidationError: If content does not meet length requirements
		"""
		if not content or not content.strip():
			raise TextValidationError("Text content cannot be empty")

		stripped = content.strip()
		length = len(stripped)

		if length < self.MIN_TEXT_LENGTH:
			raise TextValidationError(
				f"Text is too short ({length} chars). "
				f"Minimum {self.MIN_TEXT_LENGTH} characters required. "
				f"Please provide at least {self.MIN_TEXT_LENGTH} characters of content."
			)

		if length > self.MAX_TEXT_LENGTH:
			raise TextValidationError(
				f"Text is too long ({length} chars). "
				f"Maximum {self.MAX_TEXT_LENGTH} characters allowed. "
				f"Consider breaking into multiple episodes."
			)

		words = len(stripped.split())
		if words < self.MIN_WORDS_FOR_PODCAST:
			raise TextValidationError(
				f"Text has too few words ({words} words). "
				f"Minimum {self.MIN_WORDS_FOR_PODCAST} words required for podcast generation. "
				f"Expand content for better podcast generation."
			)

	async def validate_url_source(self, url: str, title: str) -> Tuple[bool, Optional[str]]:
		"""
		Validate URL source for podcast content.

		Checks URL format and accessibility via a HEAD request.

		Args:
			url: URL string to validate
			title: Source title (for logging context)

		Returns:
			Tuple of (is_valid, error_message)

		Raises:
			URLValidationError: If validation fails
		"""
		self._validate_url_format(url)
		await self._check_url_accessibility(url)
		return True, None

	async def validate_text_source(self, content: str) -> Tuple[bool, Optional[str]]:
		"""
		Validate text source content.

		Checks minimum/maximum length and word count.

		Args:
			content: Text content to validate

		Returns:
			Tuple of (is_valid, error_message)

		Raises:
			TextValidationError: If validation fails
		"""
		self._validate_text_length(content)
		return True, None

	async def validate_pdf_source(self, s3_key: str) -> Tuple[bool, Optional[str]]:
		"""
		Validate PDF source S3 key format.

		Args:
			s3_key: S3 object key

		Returns:
			Tuple of (is_valid, error_message)

		Raises:
			ValueError: If s3_key is empty
		"""
		if not s3_key or not s3_key.strip():
			raise ValueError("PDF source requires a non-empty S3 key")
		return True, None

	async def validate_by_type(self, source_type: str, source_data: dict) -> None:
		"""
		Dispatch validation based on source type.

		Args:
			source_type: One of 'url', 'pdf', 'text'
			source_data: Source data dictionary

		Raises:
			URLValidationError: For invalid URL sources
			TextValidationError: For invalid text sources
			ValueError: For invalid PDF sources
		"""
		if source_type == 'url':
			url = source_data.get('url', '')
			title = source_data.get('title', '')
			await self.validate_url_source(url, title)

		elif source_type == 'text':
			content = source_data.get('content', '')
			await self.validate_text_source(content)

		elif source_type == 'pdf':
			s3_key = source_data.get('s3_key', '')
			await self.validate_pdf_source(s3_key)
