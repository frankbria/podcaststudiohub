"""
Content extraction service for processing episode content sources.

This service wraps Podcastfy content_parser modules to extract text from URL, PDF,
and text sources. It integrates with the ContentSource model from Task 2.7 to:
- Update extraction_status (pending → extracting → complete/failed)
- Store extracted text in extracted_content column
- Store error details in error_message column

The service uses async wrappers around Podcastfy's synchronous extractors to
maintain async compatibility with the FastAPI application.
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional
from urllib.parse import urljoin
from uuid import UUID

import requests
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from requests.exceptions import RequestException, Timeout, HTTPError

from podcastfy.content_parser.website_extractor import WebsiteExtractor
from podcastfy.content_parser.pdf_extractor import PDFExtractor

from ..config import settings
from ..models import ContentSource
from ..schemas.content import ContentSourceUpdate
from ..utils.pinned_fetch import pinned_session
from ..utils.ssrf import SSRFValidationError, validate_public_url
from .content_service import get_content_source_by_id, update_content_source
from .storage_service import StorageService


logger = logging.getLogger(__name__)

# Redirect status codes that carry a Location header to follow.
_REDIRECT_STATUS = (301, 302, 303, 307, 308)
# Maximum redirect hops allowed during a single content fetch.
_MAX_REDIRECT_HOPS = 3


class ExtractionResult:
	"""
	Data structure for extraction results.

	Attributes:
		success: Whether extraction succeeded
		content: Extracted text content (None if failed)
		error_message: Error details (None if succeeded)
		word_count: Number of words in extracted content
	"""
	def __init__(
		self,
		success: bool,
		content: Optional[str] = None,
		error_message: Optional[str] = None
	):
		self.success = success
		self.content = content
		self.error_message = error_message
		self.word_count = len(content.split()) if content else 0


class ContentExtractionService:
	"""
	Service for extracting content from various sources.

	Wraps Podcastfy's synchronous content extractors with async interfaces
	and integrates with the ContentSource database model for status tracking.
	"""

	def __init__(self):
		"""Initialize the extraction service with Podcastfy extractors."""
		self.website_extractor = WebsiteExtractor()
		self.pdf_extractor = PDFExtractor()

	def _fetch_and_extract_safely(self, url: str) -> str:
		"""
		Fetch and extract URL content with SSRF-safe manual redirect handling.

		Redirects are not auto-followed: each hop is re-validated with the SSRF
		guard before it is requested, so a public URL cannot redirect the
		server-side fetch into an internal address such as the cloud metadata
		endpoint (issue #206). Podcastfy's ``WebsiteExtractor`` follows redirects
		unconditionally, so this performs the fetch itself and reuses the
		extractor's parsing helpers for output consistency.

		Args:
			url: URL to fetch.

		Returns:
			Cleaned text content.

		Raises:
			SSRFValidationError: If the URL (or a redirect target) is internal.
			requests.RequestException: On network/HTTP errors.
		"""
		extractor = self.website_extractor
		headers = {"User-Agent": extractor.user_agent}
		current_url = extractor.normalize_url(url)

		for _ in range(_MAX_REDIRECT_HOPS + 1):
			resolved = validate_public_url(
				current_url,
				allowed_ports={80, 443},
				block_on_resolution_failure=True,
			)
			# Pin the connection to the validated IP so the client cannot
			# re-resolve the host to an internal address (DNS rebinding, #234).
			with pinned_session(current_url, resolved[0]) as session:
				response = session.get(
					current_url,
					headers=headers,
					timeout=extractor.timeout,
					allow_redirects=False,
				)
			if response.status_code in _REDIRECT_STATUS:
				location = response.headers.get("location")
				if not location:
					break
				current_url = urljoin(current_url, location)
				continue

			response.raise_for_status()
			soup = BeautifulSoup(response.text, "html.parser")
			extractor.remove_unwanted_elements(soup)
			return extractor.clean_content(soup.get_text(separator="\n"))

		raise requests.TooManyRedirects(
			f"Exceeded the maximum of {_MAX_REDIRECT_HOPS} redirects"
		)

	async def extract_from_url(
		self,
		db: AsyncSession,
		content_source_id: UUID
	) -> ExtractionResult:
		"""
		Extract content from a URL source.

		Retrieves content source, validates it's a URL type, extracts content
		using Podcastfy's WebsiteExtractor, and updates the database with
		results or error details.

		Args:
			db: Database session
			content_source_id: UUID of content source to extract

		Returns:
			ExtractionResult with success status and extracted content or error

		Raises:
			ValueError: If content source not found or not URL type
		"""
		# Retrieve content source
		content_source = await get_content_source_by_id(db, content_source_id)
		if not content_source:
			raise ValueError(f"Content source {content_source_id} not found")

		# Validate source type
		if content_source.source_type != 'url':
			raise ValueError(
				f"Content source {content_source_id} is type '{content_source.source_type}', "
				"expected 'url'"
			)

		# Extract URL from source_data
		url = content_source.source_data.get('url')
		if not url:
			error_msg = "URL source missing 'url' field in source_data"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# SSRF guard: re-validate the host at dispatch time (block unresolvable
		# hosts here too — this is the actual fetch path, so a host that fails
		# the lookup but resolves to an internal IP must not slip through).
		try:
			validate_public_url(
				url, allowed_ports={80, 443}, block_on_resolution_failure=True
			)
		except SSRFValidationError as exc:
			error_msg = "URL is not allowed: targets a non-public address."
			logger.warning(f"Blocked SSRF extraction for {url}: {exc}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# Update status to 'extracting'
		await self._update_extraction_status(db, content_source, 'extracting')

		try:
			# Extract content with SSRF-safe, redirect-validating fetch.
			logger.info(f"Extracting content from URL: {url}")
			extracted_text = await asyncio.to_thread(
				self._fetch_and_extract_safely,
				url
			)

			# Update with success
			await self._update_extraction_complete(db, content_source, extracted_text)

			logger.info(
				f"Successfully extracted {len(extracted_text)} characters from {url}"
			)
			return ExtractionResult(success=True, content=extracted_text)

		except SSRFValidationError as exc:
			# A redirect target resolved to an internal address mid-fetch.
			error_msg = "URL is not allowed: targets a non-public address."
			logger.warning(f"Blocked SSRF redirect during extraction of {url}: {exc}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		except RequestException as e:
			# Handle HTTP/network errors
			error_msg = self._format_request_error(e, url)
			logger.error(f"Request error extracting {url}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		except Exception as e:
			# Handle unexpected errors
			error_msg = f"Unexpected error extracting content: {str(e)}"
			logger.exception(f"Error extracting {url}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

	async def extract_from_pdf(
		self,
		db: AsyncSession,
		content_source_id: UUID
	) -> ExtractionResult:
		"""
		Extract content from a PDF source.

		Retrieves content source, validates it's a PDF type, downloads the PDF from
		S3 (via StorageService) to a temp file, extracts content using Podcastfy's
		PDFExtractor, and updates the database with results or error details.

		Args:
			db: Database session
			content_source_id: UUID of content source to extract

		Returns:
			ExtractionResult with success status and extracted content or error

		Raises:
			ValueError: If content source not found or not PDF type
		"""
		# Retrieve content source
		content_source = await get_content_source_by_id(db, content_source_id)
		if not content_source:
			raise ValueError(f"Content source {content_source_id} not found")

		# Validate source type
		if content_source.source_type != 'pdf':
			raise ValueError(
				f"Content source {content_source_id} is type '{content_source.source_type}', "
				"expected 'pdf'"
			)

		# Extract PDF file location from source_data
		s3_key = content_source.source_data.get('s3_key')
		filename = content_source.source_data.get('filename')

		if not s3_key or not filename:
			error_msg = "PDF source missing 's3_key' or 'filename' in source_data"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# The PDF lives in S3 under s3_key (written by the upload endpoint). Without
		# a configured bucket there is nothing to download from, so fail clearly
		# rather than reading a non-existent local path.
		bucket = getattr(settings, "AWS_S3_BUCKET", None)
		if not bucket:
			error_msg = "File storage not configured; cannot retrieve PDF for extraction"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# Update status to 'extracting'
		await self._update_extraction_status(db, content_source, 'extracting')

		# Download the PDF from S3 to a temp file, extract, then always clean up.
		storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)
		temp_path: Optional[str] = None
		try:
			with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
				temp_path = tmp.name

			logger.info(f"Downloading PDF {filename} from S3 key {s3_key}")
			await storage.download_file(s3_key, temp_path)

			# Extract content using Podcastfy (sync extractor in a worker thread)
			logger.info(f"Extracting content from PDF: {filename}")
			extracted_text = await asyncio.to_thread(
				self.pdf_extractor.extract_content,
				temp_path
			)

			# Update with success
			await self._update_extraction_complete(db, content_source, extracted_text)

			logger.info(
				f"Successfully extracted {len(extracted_text)} characters from PDF {filename}"
			)
			return ExtractionResult(success=True, content=extracted_text)

		except FileNotFoundError:
			error_msg = f"PDF file not found in storage (s3_key: {s3_key})"
			logger.error(f"File error extracting {filename}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		except Exception as e:
			# Handle download failures and PDF extraction errors (corrupted file, etc.)
			error_msg = f"Error extracting PDF content: {str(e)}"
			logger.exception(f"Error extracting {filename}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		finally:
			# Always remove the downloaded temp file, even on failure.
			if temp_path and os.path.exists(temp_path):
				try:
					os.unlink(temp_path)
				except OSError:
					logger.warning(f"Failed to remove temp PDF file: {temp_path}")

	async def extract_from_text(
		self,
		db: AsyncSession,
		content_source_id: UUID
	) -> ExtractionResult:
		"""
		Extract content from a text source.

		Retrieves content source, validates it's a text type, extracts content
		directly from source_data (no external processing needed), and updates
		the database with the content.

		Args:
			db: Database session
			content_source_id: UUID of content source to extract

		Returns:
			ExtractionResult with success status and content

		Raises:
			ValueError: If content source not found or not text type
		"""
		# Retrieve content source
		content_source = await get_content_source_by_id(db, content_source_id)
		if not content_source:
			raise ValueError(f"Content source {content_source_id} not found")

		# Validate source type
		if content_source.source_type != 'text':
			raise ValueError(
				f"Content source {content_source_id} is type '{content_source.source_type}', "
				"expected 'text'"
			)

		# Extract content from source_data
		text_content = content_source.source_data.get('content')

		if not text_content:
			error_msg = "Text source missing 'content' field in source_data"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# Validate non-empty content
		if not text_content.strip():
			error_msg = "Text source has empty content"
			logger.warning(f"Content source {content_source_id}: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# Update status to 'extracting' then 'complete'
		await self._update_extraction_status(db, content_source, 'extracting')

		try:
			# Store content in extracted_content column
			await self._update_extraction_complete(db, content_source, text_content)

			logger.info(
				f"Successfully stored {len(text_content)} characters from text source"
			)
			return ExtractionResult(success=True, content=text_content)

		except Exception as e:
			error_msg = f"Error storing text content: {str(e)}"
			logger.exception(f"Error processing text source: {error_msg}")
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

	# ========================================================================
	# HELPER METHODS
	# ========================================================================

	async def _update_extraction_status(
		self,
		db: AsyncSession,
		content_source: ContentSource,
		status: str
	) -> None:
		"""Update content source extraction status."""
		update_data = ContentSourceUpdate(extraction_status=status)
		await update_content_source(db, content_source, update_data)

	async def _update_extraction_complete(
		self,
		db: AsyncSession,
		content_source: ContentSource,
		extracted_text: str
	) -> None:
		"""Update content source with successful extraction results."""
		update_data = ContentSourceUpdate(
			extraction_status='complete',
			extracted_content=extracted_text,
			error_message=None  # Clear any previous errors
		)
		await update_content_source(db, content_source, update_data)

	async def _update_extraction_failed(
		self,
		db: AsyncSession,
		content_source: ContentSource,
		error_message: str
	) -> None:
		"""Update content source with extraction failure."""
		update_data = ContentSourceUpdate(
			extraction_status='failed',
			error_message=error_message
		)
		await update_content_source(db, content_source, update_data)

	def _format_request_error(self, error: RequestException, url: str) -> str:
		"""Format request error with specific error type details."""
		if isinstance(error, Timeout):
			return f"Request timeout accessing {url}"
		elif isinstance(error, HTTPError):
			status_code = error.response.status_code if hasattr(error, 'response') else 'unknown'
			if status_code == 404:
				return f"URL not found (404): {url}"
			elif status_code == 403:
				return f"Access forbidden (403): {url}"
			elif status_code == 500:
				return f"Server error (500): {url}"
			else:
				return f"HTTP error ({status_code}): {url}"
		else:
			return f"Network error accessing {url}: {str(error)}"
