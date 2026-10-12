"""
Content extraction service for processing episode content sources.

This service extracts text from URL, PDF and text sources (the parsing itself
lives in text_extraction.py). It integrates with the ContentSource model to:
- Update extraction_status (pending → extracting → complete/failed)
- Store extracted text in extracted_content column
- Store error details in error_message column

The synchronous fetch/parse steps run in worker threads so the FastAPI
application stays async.
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse
from uuid import UUID

import requests
from sqlalchemy.ext.asyncio import AsyncSession
from requests.exceptions import RequestException, Timeout, HTTPError

from youtube_transcript_api import YouTubeTranscriptApi

from ..config import settings
from ..models import ContentSource
from ..schemas.content import ContentSourceUpdate
from ..utils.pinned_fetch import pinned_session
from ..utils.ssrf import SSRFValidationError, validate_public_url
from .content_service import get_content_source_by_id, update_content_source
from .storage_service import StorageService
from .text_extraction import (
	FETCH_TIMEOUT_SECONDS,
	USER_AGENT,
	html_to_text,
	normalize_url,
	pdf_to_text,
)


logger = logging.getLogger(__name__)

# Exact hosts, not substrings: a substring match ("youtube.com" anywhere in
# the URL) would count youtube.com.evil.test as YouTube.
_YOUTUBE_HOSTS = frozenset(
	{"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)
# Caption-only cues dropped from the transcript, as the previous engine did.
_CAPTION_CUES = frozenset({"[music]"})


def _remove_temp_file(path: Optional[str]) -> None:
	if path and os.path.exists(path):
		try:
			os.unlink(path)
		except OSError:
			logger.warning(f"Failed to remove temp PDF file: {path}")


def _youtube_video_id(url: str) -> Optional[str]:
	"""The video id of a YouTube URL, or None when the URL is not YouTube."""
	parsed = urlparse(url)
	host = parsed.hostname  # already lowercased by urlparse; None for no host
	if host not in _YOUTUBE_HOSTS:
		return None
	if host == "youtu.be":
		video_id = parsed.path.strip("/").split("/")[0]
	elif parsed.path.startswith("/shorts/"):
		video_id = parsed.path.split("/")[2]
	else:
		video_id = parse_qs(parsed.query).get("v", [""])[0]
	if not video_id:
		raise ValueError(f"YouTube URL has no video id: {url}")
	return video_id


def _youtube_transcript(video_id: str) -> str:
	snippets = YouTubeTranscriptApi().fetch(video_id)
	return " ".join(
		snippet.text for snippet in snippets
		if snippet.text.strip().lower() not in _CAPTION_CUES
	)

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

	Runs the synchronous fetch/parse steps (src/services/text_extraction.py)
	behind async interfaces and records progress on the ContentSource row.
	"""

	def fetch_url_text(self, url: str) -> str:
		"""
		Fetch and extract URL content with SSRF-safe manual redirect handling.

		Redirects are not auto-followed: each hop is re-validated with the SSRF
		guard before it is requested, so a public URL cannot redirect the
		server-side fetch into an internal address such as the cloud metadata
		endpoint (issue #206). A plain ``requests.get`` follows redirects
		unconditionally, so this performs each hop itself.

		Args:
			url: URL to fetch.

		Returns:
			Cleaned text content.

		Raises:
			SSRFValidationError: If the URL (or a redirect target) is internal.
			requests.RequestException: On network/HTTP errors.
			ValueError: For a YouTube URL that names no video.
		"""
		# A YouTube page is the video's transcript, not its watch-page HTML (the
		# behaviour the previous engine had, #543). The request goes to YouTube's own API
		# host, not the user-supplied URL, so the SSRF path below does not apply.
		# Normalised first: urlparse finds no host in a scheme-less URL, so
		# "youtube.com/watch?v=…" would otherwise miss the transcript branch.
		current_url = normalize_url(url)
		video_id = _youtube_video_id(current_url)
		if video_id:
			return _youtube_transcript(video_id)
		headers = {"User-Agent": USER_AGENT}

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
					timeout=FETCH_TIMEOUT_SECONDS,
					allow_redirects=False,
				)
			if response.status_code in _REDIRECT_STATUS:
				location = response.headers.get("location")
				if not location:
					break
				current_url = urljoin(current_url, location)
				continue

			response.raise_for_status()
			return html_to_text(response.text)

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
		with the SSRF-safe fetch_url_text, and updates the database with
		results or error details.

		Args:
			db: Database session
			content_source_id: UUID of content source to extract

		Returns:
			ExtractionResult with success status and extracted content or error

		Raises:
			ValueError: If content source not found or not URL type
		"""
		content_source = await self._source_of_type(db, content_source_id, 'url')
		url = content_source.source_data.get('url')
		error_msg = self._precheck_url(url, content_source_id)
		if error_msg:
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# Update status to 'extracting'
		await self._update_extraction_status(db, content_source, 'extracting')

		try:
			# Extract content with SSRF-safe, redirect-validating fetch.
			logger.info(f"Extracting content from URL: {url}")
			extracted_text = await asyncio.to_thread(
				self.fetch_url_text,
				url
			)

			# Update with success
			await self._update_extraction_complete(db, content_source, extracted_text)
		except Exception as e:  # noqa: BLE001 — every extraction failure must end as a recorded 'failed' status with a user-facing message, never an unhandled error leaving the source 'extracting'; _extraction_error_message logs each kind (logger.exception for the unexpected)
			error_msg = self._extraction_error_message(e, url)
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		logger.info(
			f"Successfully extracted {len(extracted_text)} characters from {url}"
		)
		return ExtractionResult(success=True, content=extracted_text)

	async def _source_of_type(self, db: AsyncSession, content_source_id: UUID, kind: str):
		"""The content source, which must exist and be of type ``kind``."""
		content_source = await get_content_source_by_id(db, content_source_id)
		if not content_source:
			raise ValueError(f"Content source {content_source_id} not found")
		if content_source.source_type != kind:
			raise ValueError(
				f"Content source {content_source_id} is type '{content_source.source_type}', "
				f"expected '{kind}'"
			)
		return content_source

	def _precheck_url(self, url: Optional[str], content_source_id: UUID) -> Optional[str]:
		"""Why ``url`` must not be fetched at all, or None when it may be."""
		if not url:
			error_msg = "URL source missing 'url' field in source_data"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			return error_msg
		# SSRF guard: re-validate the host at dispatch time (block unresolvable
		# hosts here too — this is the actual fetch path, so a host that fails
		# the lookup but resolves to an internal IP must not slip through).
		try:
			validate_public_url(
				url, allowed_ports={80, 443}, block_on_resolution_failure=True
			)
		except SSRFValidationError as exc:
			logger.warning(f"Blocked SSRF extraction for {url}: {exc}")
			return "URL is not allowed: targets a non-public address."
		return None

	def _extraction_error_message(self, exc: Exception, url: str) -> str:
		"""Log a failed fetch the way its kind deserves and return the user message."""
		if isinstance(exc, SSRFValidationError):
			# A redirect target resolved to an internal address mid-fetch.
			logger.warning(f"Blocked SSRF redirect during extraction of {url}: {exc}")
			return "URL is not allowed: targets a non-public address."
		if isinstance(exc, RequestException):
			# Handle HTTP/network errors
			error_msg = self._format_request_error(exc, url)
			logger.error(f"Request error extracting {url}: {error_msg}")
			return error_msg
		# Handle unexpected errors
		error_msg = f"Unexpected error extracting content: {str(exc)}"
		logger.exception(f"Error extracting {url}: {error_msg}")
		return error_msg

	async def extract_from_pdf(
		self,
		db: AsyncSession,
		content_source_id: UUID
	) -> ExtractionResult:
		"""
		Extract content from a PDF source.

		Retrieves content source, validates it's a PDF type, downloads the PDF from
		S3 (via StorageService) to a temp file, extracts its text with pymupdf,
		and updates the database with results or error details.

		Args:
			db: Database session
			content_source_id: UUID of content source to extract

		Returns:
			ExtractionResult with success status and extracted content or error

		Raises:
			ValueError: If content source not found or not PDF type
		"""
		content_source = await self._source_of_type(db, content_source_id, 'pdf')
		s3_key = content_source.source_data.get('s3_key')
		filename = content_source.source_data.get('filename')
		error_msg = self._precheck_pdf(s3_key, filename, content_source_id)
		if error_msg:
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		# Update status to 'extracting'
		await self._update_extraction_status(db, content_source, 'extracting')

		try:
			extracted_text = await self._download_and_extract_pdf(s3_key, filename)
			# Update with success
			await self._update_extraction_complete(db, content_source, extracted_text)
		except Exception as e:  # noqa: BLE001 — every extraction failure (download, corrupt PDF, DB write) must end as a recorded 'failed' status with a message, never a source stuck 'extracting'; _pdf_error_message logs each kind (logger.exception for the unexpected)
			error_msg = self._pdf_error_message(e, s3_key, filename)
			await self._update_extraction_failed(db, content_source, error_msg)
			return ExtractionResult(success=False, error_message=error_msg)

		logger.info(
			f"Successfully extracted {len(extracted_text)} characters from PDF {filename}"
		)
		return ExtractionResult(success=True, content=extracted_text)

	def _precheck_pdf(
		self, s3_key: Optional[str], filename: Optional[str], content_source_id: UUID
	) -> Optional[str]:
		"""Why the PDF cannot be extracted at all, or None when it can."""
		if not s3_key or not filename:
			error_msg = "PDF source missing 's3_key' or 'filename' in source_data"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			return error_msg
		# The PDF lives in S3 under s3_key (written by the upload endpoint). Without
		# a configured bucket there is nothing to download from, so fail clearly
		# rather than reading a non-existent local path.
		if not getattr(settings, "AWS_S3_BUCKET", None):
			error_msg = "File storage not configured; cannot retrieve PDF for extraction"
			logger.error(f"Content source {content_source_id}: {error_msg}")
			return error_msg
		return None

	async def _download_and_extract_pdf(self, s3_key: str, filename: str) -> str:
		"""Download the PDF to a temp file, extract its text, always clean up."""
		storage = StorageService(
			bucket_name=settings.AWS_S3_BUCKET, region_name=settings.AWS_REGION
		)
		temp_path: Optional[str] = None
		try:
			with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
				temp_path = tmp.name
			logger.info(f"Downloading PDF {filename} from S3 key {s3_key}")
			await storage.download_file(s3_key, temp_path)
			logger.info(f"Extracting content from PDF: {filename}")
			return await asyncio.to_thread(pdf_to_text, temp_path)
		finally:
			# Always remove the downloaded temp file, even on failure.
			_remove_temp_file(temp_path)

	def _pdf_error_message(self, exc: Exception, s3_key: str, filename: str) -> str:
		"""Log a failed PDF extraction the way its kind deserves; return the message."""
		if isinstance(exc, FileNotFoundError):
			error_msg = f"PDF file not found in storage (s3_key: {s3_key})"
			logger.error(f"File error extracting {filename}: {error_msg}")
			return error_msg
		# Download failures and PDF extraction errors (corrupted file, etc.)
		error_msg = f"Error extracting PDF content: {str(exc)}"
		logger.exception(f"Error extracting {filename}: {error_msg}")
		return error_msg

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
