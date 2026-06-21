"""
Comprehensive test suite for content extraction service.

Tests cover:
- URL extraction (success, 404, timeout, HTTP errors)
- PDF extraction (success, file not found, corrupted file)
- Text extraction (success, empty content, validation)
- Extraction status transitions (pending → extracting → complete/failed)
- Database updates (extracted_content, error_message columns)
- Error handling for all common failure cases

Podcastfy modules are mocked to avoid external dependencies.
"""

import os
import pytest
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4
from requests.exceptions import Timeout, HTTPError

from src.services.content_extraction_service import (
	ContentExtractionService,
	ExtractionResult
)
from src.models import ContentSource
from src.utils.ssrf import SSRFValidationError


# ============================================================================
# HELPERS
# ============================================================================

def _cleanup_leaked_temp(mock_unlink):
	"""Remove the real temp file that a patched ``os.unlink`` spy spared."""
	if mock_unlink.call_args:
		path = mock_unlink.call_args[0][0]
		if path and os.path.exists(path):
			os.unlink(path)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def extraction_service():
	"""Create ContentExtractionService instance."""
	return ContentExtractionService()


@pytest.fixture
def mock_db():
	"""Create mock database session."""
	return AsyncMock()


@pytest.fixture
def url_content_source():
	"""Create URL-type content source."""
	return ContentSource(
		id=uuid4(),
		episode_id=uuid4(),
		tenant_id=uuid4(),
		source_type='url',
		source_data={
			'url': 'https://example.com/article',
			'title': 'Test Article'
		},
		extraction_status='pending',
		extracted_content=None,
		error_message=None
	)


@pytest.fixture
def pdf_content_source():
	"""Create PDF-type content source."""
	return ContentSource(
		id=uuid4(),
		episode_id=uuid4(),
		tenant_id=uuid4(),
		source_type='pdf',
		source_data={
			'filename': 'document.pdf',
			's3_key': 'uploads/document.pdf'
		},
		extraction_status='pending',
		extracted_content=None,
		error_message=None
	)


@pytest.fixture
def text_content_source():
	"""Create text-type content source."""
	return ContentSource(
		id=uuid4(),
		episode_id=uuid4(),
		tenant_id=uuid4(),
		source_type='text',
		source_data={
			'content': 'This is raw text content for the podcast episode.'
		},
		extraction_status='pending',
		extracted_content=None,
		error_message=None
	)


# ============================================================================
# URL EXTRACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_extract_from_url_success(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test successful URL content extraction."""
	extracted_text = "This is the extracted content from the article."

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', return_value=extracted_text):

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is True
		assert result.content == extracted_text
		assert result.error_message is None
		assert result.word_count == len(extracted_text.split())

		# Verify database updates
		assert mock_update.call_count == 2  # extracting, then complete

		# First call: status to 'extracting'
		first_call = mock_update.call_args_list[0]
		assert first_call[0][1] == url_content_source
		assert first_call[0][2].extraction_status == 'extracting'

		# Second call: status to 'complete' with content
		second_call = mock_update.call_args_list[1]
		assert second_call[0][2].extraction_status == 'complete'
		assert second_call[0][2].extracted_content == extracted_text
		assert second_call[0][2].error_message is None


@pytest.mark.asyncio
@pytest.mark.parametrize("internal_url", [
	"http://169.254.169.254/latest/meta-data/",
	"http://127.0.0.1/",
	"http://10.0.0.1/admin",
	"http://192.168.1.1/",
])
async def test_extract_from_url_blocks_ssrf(
	extraction_service,
	mock_db,
	url_content_source,
	internal_url,
):
	"""Internal/metadata URLs must be blocked at extraction dispatch (issue #206)."""
	url_content_source.source_data = {'url': internal_url, 'title': 'x'}

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely') as mock_extract:

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is False
		assert "not allowed" in result.error_message.lower()
		# The underlying fetcher must never be reached.
		mock_extract.assert_not_called()
		# Status must be marked failed.
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


def _mock_pinned_session(*responses):
	"""A fake pinned_session() context manager whose .get yields ``responses``."""
	session = Mock()
	session.__enter__ = Mock(return_value=session)
	session.__exit__ = Mock(return_value=False)
	session.get.side_effect = list(responses)
	return session


def test_fetch_and_extract_safely_blocks_redirect_to_internal(extraction_service):
	"""SSRF: a redirect whose target is internal must be blocked mid-fetch (issue #206)."""
	redirect = Mock()
	redirect.status_code = 302
	redirect.headers = {"location": "http://169.254.169.254/latest/meta-data/"}

	with patch(
		"src.services.content_extraction_service.pinned_session",
		return_value=_mock_pinned_session(redirect),
	):
		with pytest.raises(SSRFValidationError):
			extraction_service._fetch_and_extract_safely("https://93.184.216.34/start")


def test_fetch_and_extract_safely_follows_safe_redirect(extraction_service):
	"""A redirect to another public URL is followed and its content extracted."""
	redirect = Mock()
	redirect.status_code = 302
	redirect.headers = {"location": "https://8.8.8.8/final"}
	ok = Mock()
	ok.status_code = 200
	ok.text = "<html><body><p>Hello world content</p></body></html>"
	ok.raise_for_status = Mock()

	with patch(
		"src.services.content_extraction_service.pinned_session",
		return_value=_mock_pinned_session(redirect, ok),
	):
		result = extraction_service._fetch_and_extract_safely("https://93.184.216.34/start")

	assert "Hello world content" in result


def test_fetch_and_extract_safely_pins_validated_ip(extraction_service):
	"""The fetch must connect via a session pinned to the guard-validated IP (#234)."""
	ok = Mock()
	ok.status_code = 200
	ok.text = "<html><body><p>pinned content</p></body></html>"
	ok.raise_for_status = Mock()

	with patch(
		"src.services.content_extraction_service.pinned_session",
		return_value=_mock_pinned_session(ok),
	) as mock_pinned:
		result = extraction_service._fetch_and_extract_safely("https://93.184.216.34/start")

	assert "pinned content" in result
	# pinned_session was given the validated IP literal (here the host itself).
	mock_pinned.assert_called_once_with("https://93.184.216.34/start", "93.184.216.34")


@pytest.mark.asyncio
async def test_extract_from_url_404_error(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test URL extraction with 404 error."""
	http_error = HTTPError()
	http_error.response = Mock(status_code=404)

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', side_effect=http_error):

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is False
		assert result.content is None
		assert "404" in result.error_message
		assert "not found" in result.error_message.lower()

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'
		assert final_call[0][2].error_message is not None


@pytest.mark.asyncio
async def test_extract_from_url_timeout(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test URL extraction with timeout error."""
	timeout_error = Timeout("Connection timeout")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', side_effect=timeout_error):

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is False
		assert "timeout" in result.error_message.lower()

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_url_403_error(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test URL extraction with 403 forbidden error."""
	http_error = HTTPError()
	http_error.response = Mock(status_code=403)

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source'), \
		 patch.object(extraction_service, '_fetch_and_extract_safely', side_effect=http_error):

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is False
		assert "403" in result.error_message
		assert "forbidden" in result.error_message.lower()


@pytest.mark.asyncio
async def test_extract_from_url_500_error(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test URL extraction with 500 server error."""
	http_error = HTTPError()
	http_error.response = Mock(status_code=500)

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source'), \
		 patch.object(extraction_service, '_fetch_and_extract_safely', side_effect=http_error):

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is False
		assert "500" in result.error_message
		assert "server error" in result.error_message.lower()


@pytest.mark.asyncio
async def test_extract_from_url_missing_url_field(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test URL extraction when source_data missing 'url' field."""
	url_content_source.source_data = {'title': 'Test'}  # Missing 'url'

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update:

		mock_get.return_value = url_content_source

		result = await extraction_service.extract_from_url(mock_db, url_content_source.id)

		assert result.success is False
		assert "missing 'url' field" in result.error_message.lower()

		# Verify failure status update
		assert mock_update.call_count == 1
		assert mock_update.call_args[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_url_wrong_type(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test URL extraction on non-URL content source raises ValueError."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get:
		mock_get.return_value = pdf_content_source

		with pytest.raises(ValueError, match="expected 'url'"):
			await extraction_service.extract_from_url(mock_db, pdf_content_source.id)


@pytest.mark.asyncio
async def test_extract_from_url_not_found(extraction_service, mock_db):
	"""Test URL extraction when content source not found raises ValueError."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get:
		mock_get.return_value = None

		with pytest.raises(ValueError, match="not found"):
			await extraction_service.extract_from_url(mock_db, uuid4())


# ============================================================================
# PDF EXTRACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_extract_from_pdf_success(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test successful PDF content extraction: downloads from S3, extracts, cleans up."""
	extracted_text = "This is the extracted content from the PDF document."

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.settings.AWS_S3_BUCKET', 'test-bucket'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.os.unlink') as mock_unlink, \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', return_value=extracted_text):

		mock_storage = mock_storage_cls.return_value
		mock_storage.download_file = AsyncMock(return_value="/tmp/downloaded.pdf")
		mock_get.return_value = pdf_content_source

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is True
		assert result.content == extracted_text
		assert result.error_message is None
		assert result.word_count == len(extracted_text.split())

		# Verify the PDF was downloaded from S3 with the stored s3_key
		mock_storage.download_file.assert_awaited_once()
		download_args = mock_storage.download_file.call_args[0]
		assert download_args[0] == pdf_content_source.source_data['s3_key']

		# The downloaded temp path is what gets extracted (not a data/uploads path)
		extract_path = extraction_service.pdf_extractor.extract_content.call_args[0][0]
		assert extract_path == download_args[1]

		# Temp file is always cleaned up
		mock_unlink.assert_called_once()
		_cleanup_leaked_temp(mock_unlink)

		# Verify database updates
		assert mock_update.call_count == 2  # extracting, then complete

		# Verify final status is 'complete'
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'complete'
		assert final_call[0][2].extracted_content == extracted_text


@pytest.mark.asyncio
async def test_extract_from_pdf_file_not_found(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction when the extractor raises FileNotFoundError."""
	file_error = FileNotFoundError("File not found")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.settings.AWS_S3_BUCKET', 'test-bucket'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.os.unlink') as mock_unlink, \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', side_effect=file_error):

		mock_storage = mock_storage_cls.return_value
		mock_storage.download_file = AsyncMock(return_value="/tmp/downloaded.pdf")
		mock_get.return_value = pdf_content_source

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert result.content is None
		assert "not found" in result.error_message.lower()
		# Error references the S3 key, not the old hard-coded local path
		assert pdf_content_source.source_data['s3_key'] in result.error_message
		assert "data/uploads" not in result.error_message

		# Temp file still cleaned up on failure
		mock_unlink.assert_called_once()
		_cleanup_leaked_temp(mock_unlink)

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_corrupted_file(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction with corrupted file error."""
	extraction_error = Exception("PDF extraction failed: corrupted file")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.settings.AWS_S3_BUCKET', 'test-bucket'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.os.unlink') as mock_unlink, \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', side_effect=extraction_error):

		mock_storage = mock_storage_cls.return_value
		mock_storage.download_file = AsyncMock(return_value="/tmp/downloaded.pdf")
		mock_get.return_value = pdf_content_source

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "corrupted file" in result.error_message.lower()

		mock_unlink.assert_called_once()
		_cleanup_leaked_temp(mock_unlink)

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_storage_not_configured(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""PDF extraction fails clearly when S3 is not configured (no dead local path)."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.settings.AWS_S3_BUCKET', None):

		mock_get.return_value = pdf_content_source

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "not configured" in result.error_message.lower()

		# Only the failure update — extraction never started
		assert mock_update.call_count == 1
		assert mock_update.call_args[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_download_failure(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""PDF extraction fails (and cleans up) when the S3 download errors."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.settings.AWS_S3_BUCKET', 'test-bucket'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.os.unlink') as mock_unlink:

		mock_storage = mock_storage_cls.return_value
		mock_storage.download_file = AsyncMock(
			side_effect=Exception("Failed to download file from S3: NoSuchKey")
		)
		mock_get.return_value = pdf_content_source

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "error extracting pdf content" in result.error_message.lower()

		mock_unlink.assert_called_once()
		_cleanup_leaked_temp(mock_unlink)

		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_missing_fields(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction when source_data missing required fields."""
	pdf_content_source.source_data = {'filename': 'test.pdf'}  # Missing 's3_key'

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update:

		mock_get.return_value = pdf_content_source

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "missing" in result.error_message.lower()

		# Verify failure status update
		assert mock_update.call_count == 1
		assert mock_update.call_args[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_wrong_type(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test PDF extraction on non-PDF content source raises ValueError."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get:
		mock_get.return_value = url_content_source

		with pytest.raises(ValueError, match="expected 'pdf'"):
			await extraction_service.extract_from_pdf(mock_db, url_content_source.id)


@pytest.mark.asyncio
async def test_extract_from_pdf_not_found(extraction_service, mock_db):
	"""Test PDF extraction when content source not found raises ValueError."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get:
		mock_get.return_value = None

		with pytest.raises(ValueError, match="not found"):
			await extraction_service.extract_from_pdf(mock_db, uuid4())


# ============================================================================
# TEXT EXTRACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_extract_from_text_success(
	extraction_service,
	mock_db,
	text_content_source
):
	"""Test successful text content extraction."""
	text_content = text_content_source.source_data['content']

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update:

		mock_get.return_value = text_content_source

		result = await extraction_service.extract_from_text(mock_db, text_content_source.id)

		assert result.success is True
		assert result.content == text_content
		assert result.error_message is None
		assert result.word_count == len(text_content.split())

		# Verify database updates
		assert mock_update.call_count == 2  # extracting, then complete

		# Verify final status is 'complete'
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'complete'
		assert final_call[0][2].extracted_content == text_content


@pytest.mark.asyncio
async def test_extract_from_text_empty_content(
	extraction_service,
	mock_db,
	text_content_source
):
	"""Test text extraction with empty content."""
	text_content_source.source_data = {'content': '   '}  # Whitespace only

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update:

		mock_get.return_value = text_content_source

		result = await extraction_service.extract_from_text(mock_db, text_content_source.id)

		assert result.success is False
		assert "empty content" in result.error_message.lower()

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_text_missing_content_field(
	extraction_service,
	mock_db,
	text_content_source
):
	"""Test text extraction when source_data missing 'content' field."""
	text_content_source.source_data = {}  # Missing 'content'

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update:

		mock_get.return_value = text_content_source

		result = await extraction_service.extract_from_text(mock_db, text_content_source.id)

		assert result.success is False
		assert "missing 'content' field" in result.error_message.lower()

		# Verify failure status update
		assert mock_update.call_count == 1
		assert mock_update.call_args[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_text_wrong_type(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test text extraction on non-text content source raises ValueError."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get:
		mock_get.return_value = url_content_source

		with pytest.raises(ValueError, match="expected 'text'"):
			await extraction_service.extract_from_text(mock_db, url_content_source.id)


@pytest.mark.asyncio
async def test_extract_from_text_not_found(extraction_service, mock_db):
	"""Test text extraction when content source not found raises ValueError."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get:
		mock_get.return_value = None

		with pytest.raises(ValueError, match="not found"):
			await extraction_service.extract_from_text(mock_db, uuid4())


# ============================================================================
# EXTRACTION STATUS TRANSITION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_status_transition_url_success(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test extraction status transitions: pending → extracting → complete."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', return_value="content"):

		mock_get.return_value = url_content_source

		await extraction_service.extract_from_url(mock_db, url_content_source.id)

		# Verify status transitions
		assert mock_update.call_count == 2

		# First transition: pending → extracting
		assert mock_update.call_args_list[0][0][2].extraction_status == 'extracting'

		# Second transition: extracting → complete
		assert mock_update.call_args_list[1][0][2].extraction_status == 'complete'


@pytest.mark.asyncio
async def test_status_transition_url_failure(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test extraction status transitions: pending → extracting → failed."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', side_effect=Timeout()):

		mock_get.return_value = url_content_source

		await extraction_service.extract_from_url(mock_db, url_content_source.id)

		# Verify status transitions
		assert mock_update.call_count == 2

		# First transition: pending → extracting
		assert mock_update.call_args_list[0][0][2].extraction_status == 'extracting'

		# Second transition: extracting → failed
		assert mock_update.call_args_list[1][0][2].extraction_status == 'failed'
		assert mock_update.call_args_list[1][0][2].error_message is not None


# ============================================================================
# DATABASE UPDATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_database_update_extracted_content(
	extraction_service,
	mock_db,
	text_content_source
):
	"""Test extracted_content column is updated on success."""
	text_content = "This is the extracted text content."
	text_content_source.source_data['content'] = text_content

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update:

		mock_get.return_value = text_content_source

		await extraction_service.extract_from_text(mock_db, text_content_source.id)

		# Verify extracted_content is set
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extracted_content == text_content


@pytest.mark.asyncio
async def test_database_update_error_message(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test error_message column is updated on failure."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', side_effect=Timeout()):

		mock_get.return_value = url_content_source

		await extraction_service.extract_from_url(mock_db, url_content_source.id)

		# Verify error_message is set
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].error_message is not None
		assert "timeout" in final_call[0][2].error_message.lower()


@pytest.mark.asyncio
async def test_database_update_clears_error_on_success(
	extraction_service,
	mock_db,
	url_content_source
):
	"""Test error_message is cleared on successful extraction."""
	url_content_source.error_message = "Previous error"

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service, '_fetch_and_extract_safely', return_value="content"):

		mock_get.return_value = url_content_source

		await extraction_service.extract_from_url(mock_db, url_content_source.id)

		# Verify error_message is cleared
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].error_message is None


# ============================================================================
# EXTRACTION RESULT TESTS
# ============================================================================

def test_extraction_result_success():
	"""Test ExtractionResult for success case."""
	content = "This is extracted content with multiple words."
	result = ExtractionResult(success=True, content=content)

	assert result.success is True
	assert result.content == content
	assert result.error_message is None
	assert result.word_count == 7  # "This is extracted content with multiple words."


def test_extraction_result_failure():
	"""Test ExtractionResult for failure case."""
	error_msg = "Extraction failed due to timeout"
	result = ExtractionResult(success=False, error_message=error_msg)

	assert result.success is False
	assert result.content is None
	assert result.error_message == error_msg
	assert result.word_count == 0


def test_extraction_result_empty_content():
	"""Test ExtractionResult word count with empty content."""
	result = ExtractionResult(success=True, content="")

	assert result.word_count == 0
