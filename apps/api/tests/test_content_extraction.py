"""
Comprehensive test suite for content extraction service.

Tests cover:
- URL extraction (success, 404, timeout, HTTP errors)
- PDF extraction (success, S3 download, S3 errors, corrupted file, cleanup)
- Text extraction (success, empty content, validation)
- Extraction status transitions (pending → extracting → complete/failed)
- Database updates (extracted_content, error_message columns)
- Error handling for all common failure cases

Podcastfy modules and StorageService are mocked to avoid external dependencies.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4
from requests.exceptions import Timeout, HTTPError, RequestException

from src.services.content_extraction_service import (
	ContentExtractionService,
	ExtractionResult
)
from src.models import ContentSource
from src.schemas.content import ContentSourceUpdate


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
		 patch.object(extraction_service.website_extractor, 'extract_content', return_value=extracted_text):

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
		 patch.object(extraction_service.website_extractor, 'extract_content', side_effect=http_error):

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
		 patch.object(extraction_service.website_extractor, 'extract_content', side_effect=timeout_error):

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
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service.website_extractor, 'extract_content', side_effect=http_error):

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
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch.object(extraction_service.website_extractor, 'extract_content', side_effect=http_error):

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
	"""Test successful PDF content extraction from S3."""
	extracted_text = "This is the extracted content from the PDF document."

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove'), \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', return_value=extracted_text):

		mock_get.return_value = pdf_content_source

		# Mock temp file creation
		mock_tmp = Mock()
		mock_tmp.name = '/tmp/test_pdf.pdf'
		mock_tmpfile.return_value = mock_tmp

		# Mock StorageService instance
		mock_storage = AsyncMock()
		mock_storage_cls.return_value = mock_storage

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is True
		assert result.content == extracted_text
		assert result.error_message is None
		assert result.word_count == len(extracted_text.split())

		# Verify S3 download was called with correct args
		mock_storage.download_file.assert_called_once_with(
			s3_key='uploads/document.pdf',
			local_path='/tmp/test_pdf.pdf'
		)

		# Verify database updates
		assert mock_update.call_count == 2  # extracting, then complete

		# Verify final status is 'complete'
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'complete'
		assert final_call[0][2].extracted_content == extracted_text


@pytest.mark.asyncio
async def test_extract_from_pdf_s3_not_found(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction when S3 file is not found (404)."""
	s3_error = Exception("Failed to download file from S3: An error occurred (NoSuchKey) when calling the GetObject operation: The specified key does not exist.")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove'):

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/test_pdf.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage.download_file.side_effect = s3_error
		mock_storage_cls.return_value = mock_storage

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert result.content is None
		assert "not found in S3" in result.error_message
		assert "uploads/document.pdf" in result.error_message

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_s3_access_denied(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction when S3 returns access denied (403)."""
	s3_error = Exception("Failed to download file from S3: An error occurred (AccessDenied) when calling the GetObject operation: Access Denied")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove'):

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/test_pdf.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage.download_file.side_effect = s3_error
		mock_storage_cls.return_value = mock_storage

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "Access denied to S3 file" in result.error_message
		assert "uploads/document.pdf" in result.error_message

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_s3_generic_error(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction when S3 download fails with a generic error."""
	s3_error = Exception("Failed to download file from S3: Connection reset by peer")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove'):

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/test_pdf.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage.download_file.side_effect = s3_error
		mock_storage_cls.return_value = mock_storage

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "Failed to download PDF from S3" in result.error_message

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_corrupted_file(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test PDF extraction with corrupted file error after successful S3 download."""
	extraction_error = Exception("PDF extraction failed: corrupted file")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source') as mock_update, \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove'), \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', side_effect=extraction_error):

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/test_pdf.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage_cls.return_value = mock_storage

		result = await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		assert result.success is False
		assert "corrupted file" in result.error_message.lower()

		# Verify failure status update
		final_call = mock_update.call_args_list[-1]
		assert final_call[0][2].extraction_status == 'failed'


@pytest.mark.asyncio
async def test_extract_from_pdf_temp_file_cleanup_on_success(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test that temporary file is deleted after successful extraction."""
	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove') as mock_remove, \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', return_value="text"):

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/cleanup_test.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage_cls.return_value = mock_storage

		await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		# Verify temp file was removed
		mock_remove.assert_called_once_with('/tmp/cleanup_test.pdf')


@pytest.mark.asyncio
async def test_extract_from_pdf_temp_file_cleanup_on_error(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test that temporary file is deleted even when extraction fails."""
	extraction_error = Exception("Unexpected extraction failure")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove') as mock_remove, \
		 patch.object(extraction_service.pdf_extractor, 'extract_content', side_effect=extraction_error):

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/cleanup_error_test.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage_cls.return_value = mock_storage

		await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		# Verify temp file was removed even though extraction failed
		mock_remove.assert_called_once_with('/tmp/cleanup_error_test.pdf')


@pytest.mark.asyncio
async def test_extract_from_pdf_temp_file_cleanup_on_s3_error(
	extraction_service,
	mock_db,
	pdf_content_source
):
	"""Test that temporary file is deleted when S3 download fails."""
	s3_error = Exception("Failed to download file from S3: connection error")

	with patch('src.services.content_extraction_service.get_content_source_by_id') as mock_get, \
		 patch('src.services.content_extraction_service.update_content_source'), \
		 patch('src.services.content_extraction_service.StorageService') as mock_storage_cls, \
		 patch('src.services.content_extraction_service.tempfile.NamedTemporaryFile') as mock_tmpfile, \
		 patch('src.services.content_extraction_service.os.path.exists', return_value=True), \
		 patch('src.services.content_extraction_service.os.remove') as mock_remove:

		mock_get.return_value = pdf_content_source

		mock_tmp = Mock()
		mock_tmp.name = '/tmp/cleanup_s3_error_test.pdf'
		mock_tmpfile.return_value = mock_tmp

		mock_storage = AsyncMock()
		mock_storage.download_file.side_effect = s3_error
		mock_storage_cls.return_value = mock_storage

		await extraction_service.extract_from_pdf(mock_db, pdf_content_source.id)

		# Verify temp file was removed even though S3 download failed
		mock_remove.assert_called_once_with('/tmp/cleanup_s3_error_test.pdf')


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
		 patch.object(extraction_service.website_extractor, 'extract_content', return_value="content"):

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
		 patch.object(extraction_service.website_extractor, 'extract_content', side_effect=Timeout()):

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
		 patch.object(extraction_service.website_extractor, 'extract_content', side_effect=Timeout()):

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
		 patch.object(extraction_service.website_extractor, 'extract_content', return_value="content"):

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
