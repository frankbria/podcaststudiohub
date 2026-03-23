"""
Comprehensive test suite for script generation service.

Tests cover:
- Script generation with mocked Gemini responses (success case)
- Status transitions (draft → queued → generating → complete/failed)
- API failure handling (Gemini timeout, rate limit, invalid response)
- Content validation (no extracted content, empty content)
- Transcript validation (missing Person1/Person2 tags, malformed XML)
- Transcript file storage (file created, path saved in transcript_path)
- Multiple content sources (concatenation, separator logic)
- Template configuration application
- generation_progress JSONB updates

Podcastfy ContentGenerator and all services are mocked to avoid external dependencies.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, mock_open, call
from uuid import uuid4

from src.services.script_generation_service import (
	ScriptGenerationService,
	GenerationResult
)
from src.models import Episode, ContentSource


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def generation_service():
	"""Create ScriptGenerationService instance."""
	return ScriptGenerationService()


@pytest.fixture
def mock_db():
	"""Create mock database session."""
	return AsyncMock()


@pytest.fixture
def draft_episode():
	"""Create episode in draft status."""
	return Episode(
		id=uuid4(),
		project_id=uuid4(),
		user_id=uuid4(),
		tenant_id=uuid4(),
		episode_number=1,
		episode_metadata={"title": "Test Episode"},
		generation_status='draft',
		generation_progress={},
		transcript_path=None
	)


@pytest.fixture
def queued_episode():
	"""Create episode in queued status."""
	episode = Episode(
		id=uuid4(),
		project_id=uuid4(),
		user_id=uuid4(),
		tenant_id=uuid4(),
		episode_number=1,
		episode_metadata={"title": "Test Episode"},
		generation_status='queued',
		generation_progress={"stage": "queued", "progress": 0},
		transcript_path=None
	)
	return episode


@pytest.fixture
def url_content_source():
	"""Create URL-type completed content source."""
	return ContentSource(
		id=uuid4(),
		episode_id=uuid4(),
		tenant_id=uuid4(),
		source_type='url',
		source_data={
			'url': 'https://example.com/article',
			'title': 'Test Article'
		},
		extraction_status='complete',
		extracted_content='This is extracted content from a URL source.',
		error_message=None
	)


@pytest.fixture
def pdf_content_source():
	"""Create PDF-type completed content source."""
	return ContentSource(
		id=uuid4(),
		episode_id=uuid4(),
		tenant_id=uuid4(),
		source_type='pdf',
		source_data={
			'filename': 'document.pdf',
			's3_key': 'uploads/document.pdf'
		},
		extraction_status='complete',
		extracted_content='This is extracted content from a PDF document.',
		error_message=None
	)


@pytest.fixture
def text_content_source():
	"""Create text-type completed content source."""
	return ContentSource(
		id=uuid4(),
		episode_id=uuid4(),
		tenant_id=uuid4(),
		source_type='text',
		source_data={'content': 'Raw text content'},
		extraction_status='complete',
		extracted_content='This is raw text content for the podcast.',
		error_message=None
	)


@pytest.fixture
def valid_transcript():
	"""Sample valid transcript with Person1/Person2 tags."""
	return """<Person1>Welcome to the podcast!</Person1>
<Person2>Thanks for having me!</Person2>
<Person1>Let's discuss the topic.</Person1>
<Person2>Sure, I'd love to share my thoughts.</Person2>"""


# ============================================================================
# GENERATION SUCCESS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_script_success(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source,
	valid_transcript
):
	"""Test successful script generation with valid transcript."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode') as mock_update_episode, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript) as mock_gemini, \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(
			mock_db,
			draft_episode.id
		)

		assert result.success is True
		assert result.transcript == valid_transcript
		assert result.transcript_path is not None
		assert 'data/transcripts' in result.transcript_path
		assert result.error_message is None
		assert result.word_count > 0

		# Verify status transitions: draft → queued → generating → complete
		assert mock_update_status.call_count == 3

		# First call: queued
		first_status_call = mock_update_status.call_args_list[0]
		assert first_status_call[0][2] == 'queued'

		# Second call: generating
		second_status_call = mock_update_status.call_args_list[1]
		assert second_status_call[0][2] == 'generating'

		# Third call: complete
		third_status_call = mock_update_status.call_args_list[2]
		assert third_status_call[0][2] == 'complete'
		assert third_status_call[0][3]['stage'] == 'complete'
		assert third_status_call[0][3]['progress'] == 100

		# Verify Gemini API was called
		assert mock_gemini.called

		# Verify transcript_path was updated
		assert mock_update_episode.called


@pytest.mark.asyncio
async def test_generate_script_with_template_config(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source,
	valid_transcript
):
	"""Test script generation with custom template configuration."""
	template_config = {
		"podcast_name": "Custom Podcast",
		"roles_person1": "Host",
		"roles_person2": "Guest"
	}

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status'), \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript) as mock_gemini, \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(
			mock_db,
			draft_episode.id,
			template_config=template_config
		)

		assert result.success is True

		# Verify template_config was passed to Gemini API
		assert mock_gemini.called
		call_args = mock_gemini.call_args
		assert call_args[0][1] == template_config  # Second arg should be template_config


@pytest.mark.asyncio
async def test_generate_script_longform(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source,
	valid_transcript
):
	"""Test long-form script generation."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status'), \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript) as mock_gemini, \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(
			mock_db,
			draft_episode.id,
			longform=True
		)

		assert result.success is True

		# Verify longform flag was passed to Gemini API
		assert mock_gemini.called
		call_args = mock_gemini.call_args
		assert call_args[0][2] is True  # Third arg should be longform=True


# ============================================================================
# STATUS TRANSITION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_status_transition_draft_to_complete(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source,
	valid_transcript
):
	"""Test status transitions: draft → queued → generating → complete."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript), \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		await generation_service.generate_script(mock_db, draft_episode.id)

		# Verify all status transitions
		status_calls = [call[0][2] for call in mock_update_status.call_args_list]
		assert status_calls == ['queued', 'generating', 'complete']


@pytest.mark.asyncio
async def test_status_transition_queued_to_complete(
	generation_service,
	mock_db,
	queued_episode,
	url_content_source,
	valid_transcript
):
	"""Test status transitions from queued: queued → generating → complete."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript), \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = queued_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		await generation_service.generate_script(mock_db, queued_episode.id)

		# Should skip queued status update
		status_calls = [call[0][2] for call in mock_update_status.call_args_list]
		assert status_calls == ['generating', 'complete']


@pytest.mark.asyncio
async def test_status_transition_to_failed_on_api_error(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test status transitions on API failure: draft → queued → generating → failed."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', side_effect=Exception("API timeout")):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "API timeout" in result.error_message

		# Verify status transitions to failed
		status_calls = [call[0][2] for call in mock_update_status.call_args_list]
		assert 'failed' in status_calls


# ============================================================================
# CONTENT VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_script_no_content_sources(
	generation_service,
	mock_db,
	draft_episode
):
	"""Test generation fails when no completed content sources exist."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status:

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([], 0)  # No content sources

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "No completed content sources" in result.error_message

		# Verify status updated to failed
		final_call = mock_update_status.call_args_list[-1]
		assert final_call[0][2] == 'failed'


@pytest.mark.asyncio
async def test_generate_script_empty_content(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation fails when extracted content is empty."""
	url_content_source.extracted_content = "   "  # Whitespace only

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status:

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "Combined content is empty" in result.error_message

		# Verify status updated to failed
		final_call = mock_update_status.call_args_list[-1]
		assert final_call[0][2] == 'failed'


@pytest.mark.asyncio
async def test_generate_script_only_pending_sources(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation fails when content sources are not completed."""
	url_content_source.extraction_status = 'pending'  # Not completed

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status'):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "No completed content sources" in result.error_message


# ============================================================================
# TRANSCRIPT VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_script_invalid_transcript_missing_person1(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation fails when transcript missing Person1 tag."""
	invalid_transcript = "<Person2>Only Person2 speaking</Person2>"

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', return_value=invalid_transcript):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "missing Person1/Person2 tags" in result.error_message

		# Verify status updated to failed
		final_call = mock_update_status.call_args_list[-1]
		assert final_call[0][2] == 'failed'


@pytest.mark.asyncio
async def test_generate_script_invalid_transcript_missing_person2(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation fails when transcript missing Person2 tag."""
	invalid_transcript = "<Person1>Only Person1 speaking</Person1>"

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status'), \
		 patch.object(generation_service, '_call_gemini_api', return_value=invalid_transcript):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "missing Person1/Person2 tags" in result.error_message


# ============================================================================
# MULTIPLE CONTENT SOURCES TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_script_multiple_sources(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source,
	pdf_content_source,
	text_content_source,
	valid_transcript
):
	"""Test script generation with multiple content sources."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status'), \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript) as mock_gemini, \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = (
			[url_content_source, pdf_content_source, text_content_source],
			3
		)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is True

		# Verify combined content was passed to Gemini
		assert mock_gemini.called
		combined_content = mock_gemini.call_args[0][0]

		# Should contain content from all sources
		assert 'Test Article' in combined_content  # URL title
		assert 'document.pdf' in combined_content  # PDF filename
		assert 'Text Content' in combined_content  # Text source
		assert url_content_source.extracted_content in combined_content
		assert pdf_content_source.extracted_content in combined_content
		assert text_content_source.extracted_content in combined_content


def test_concatenate_content_with_separators(
	generation_service,
	url_content_source,
	pdf_content_source
):
	"""Test content concatenation includes source metadata and separators."""
	combined = generation_service._concatenate_content([url_content_source, pdf_content_source])

	# Should contain source metadata
	assert 'Test Article' in combined
	assert 'https://example.com/article' in combined
	assert 'document.pdf' in combined

	# Should contain extracted content
	assert url_content_source.extracted_content in combined
	assert pdf_content_source.extracted_content in combined

	# Should have separators
	assert '===' in combined


# ============================================================================
# API FAILURE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_script_gemini_timeout(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation handles Gemini API timeout."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', side_effect=TimeoutError("Request timeout")):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "timeout" in result.error_message.lower()

		# Verify status updated to failed
		final_call = mock_update_status.call_args_list[-1]
		assert final_call[0][2] == 'failed'
		assert 'error_message' in final_call[0][3]


@pytest.mark.asyncio
async def test_generate_script_gemini_api_error(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation handles Gemini API general errors."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status'), \
		 patch.object(generation_service, '_call_gemini_api', side_effect=Exception("API rate limit exceeded")):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "rate limit" in result.error_message.lower()


# ============================================================================
# EPISODE STATE VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generate_script_episode_not_found(
	generation_service,
	mock_db
):
	"""Test generation raises ValueError when episode not found."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode:
		mock_get_episode.return_value = None

		with pytest.raises(ValueError, match="not found"):
			await generation_service.generate_script(mock_db, uuid4())


@pytest.mark.asyncio
async def test_generate_script_invalid_episode_status(
	generation_service,
	mock_db,
	draft_episode
):
	"""Test generation raises ValueError when episode in invalid status."""
	draft_episode.generation_status = 'complete'  # Already completed

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode:
		mock_get_episode.return_value = draft_episode

		with pytest.raises(ValueError, match="expected 'draft' or 'queued'"):
			await generation_service.generate_script(mock_db, draft_episode.id)


# ============================================================================
# TRANSCRIPT FILE STORAGE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_save_transcript_creates_directory(
	generation_service
):
	"""Test transcript save creates directory if not exists."""
	episode_id = uuid4()
	transcript = "<Person1>Test</Person1><Person2>Test</Person2>"

	with patch('pathlib.Path.mkdir') as mock_mkdir, \
		 patch('builtins.open', mock_open()):

		await generation_service._save_transcript(episode_id, transcript)

		# Verify directory was created
		assert mock_mkdir.called
		assert mock_mkdir.call_args[1]['parents'] is True
		assert mock_mkdir.call_args[1]['exist_ok'] is True


@pytest.mark.asyncio
async def test_save_transcript_writes_file(
	generation_service
):
	"""Test transcript save writes content to file."""
	episode_id = uuid4()
	transcript = "<Person1>Test content</Person1><Person2>More content</Person2>"

	with patch('pathlib.Path.mkdir'), \
		 patch('builtins.open', mock_open()) as mock_file:

		transcript_path = await generation_service._save_transcript(episode_id, transcript)

		# Verify file was written
		assert mock_file.called
		mock_file.assert_called_once()

		# Verify transcript path
		assert str(episode_id) in transcript_path
		assert transcript_path.endswith('.xml')
		assert 'data/transcripts' in transcript_path


# ============================================================================
# GENERATION PROGRESS JSONB TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_generation_progress_updates(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source,
	valid_transcript
):
	"""Test generation_progress JSONB is updated correctly."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_episode'), \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', return_value=valid_transcript), \
		 patch('builtins.open', mock_open()):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		await generation_service.generate_script(mock_db, draft_episode.id)

		# Verify progress updates
		progress_updates = [call[0][3] for call in mock_update_status.call_args_list]

		# First update: queued with started_at
		assert progress_updates[0]['stage'] == 'queued'
		assert progress_updates[0]['progress'] == 0
		assert 'started_at' in progress_updates[0]

		# Second update: generating with progress
		assert progress_updates[1]['stage'] == 'generating'
		assert progress_updates[1]['progress'] == 50

		# Third update: complete with completed_at
		assert progress_updates[2]['stage'] == 'complete'
		assert progress_updates[2]['progress'] == 100
		assert 'completed_at' in progress_updates[2]


@pytest.mark.asyncio
async def test_generation_progress_error_message(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test generation_progress includes error_message on failure."""
	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', side_effect=Exception("Test error")):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		await generation_service.generate_script(mock_db, draft_episode.id)

		# Verify final progress update contains error_message
		final_progress = mock_update_status.call_args_list[-1][0][3]
		assert 'error_message' in final_progress
		assert 'Test error' in final_progress['error_message']


# ============================================================================
# GENERATION RESULT TESTS
# ============================================================================

def test_generation_result_success():
	"""Test GenerationResult for success case."""
	transcript = "<Person1>Test content</Person1><Person2>More test content</Person2>"
	result = GenerationResult(
		success=True,
		transcript=transcript,
		transcript_path="data/transcripts/123.xml"
	)

	assert result.success is True
	assert result.transcript == transcript
	assert result.transcript_path == "data/transcripts/123.xml"
	assert result.error_message is None
	assert result.word_count == 4  # "Test", "content", "More", "test", "content" split by spaces


def test_generation_result_failure():
	"""Test GenerationResult for failure case."""
	result = GenerationResult(
		success=False,
		error_message="Generation failed"
	)

	assert result.success is False
	assert result.transcript is None
	assert result.transcript_path is None
	assert result.error_message == "Generation failed"
	assert result.word_count == 0


# ============================================================================
# VALIDATE TRANSCRIPT METHOD TESTS
# ============================================================================

def test_validate_transcript_valid(generation_service):
	"""Test transcript validation with valid transcript."""
	valid = "<Person1>Hello</Person1><Person2>Hi</Person2>"
	assert generation_service._validate_transcript(valid) is True


def test_validate_transcript_missing_person1(generation_service):
	"""Test transcript validation fails without Person1."""
	invalid = "<Person2>Hi</Person2>"
	assert generation_service._validate_transcript(invalid) is False


def test_validate_transcript_missing_person2(generation_service):
	"""Test transcript validation fails without Person2."""
	invalid = "<Person1>Hello</Person1>"
	assert generation_service._validate_transcript(invalid) is False


def test_validate_transcript_empty(generation_service):
	"""Test transcript validation fails with empty string."""
	assert generation_service._validate_transcript("") is False


# ============================================================================
# TIMEOUT AND RETRY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_call_gemini_api_timeout_raises_timeout_error(generation_service):
	"""Test _call_gemini_api raises TimeoutError after all retries timeout."""
	with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError), \
		 patch('asyncio.sleep', new_callable=AsyncMock):

		with pytest.raises(TimeoutError) as exc_info:
			await generation_service._call_gemini_api(
				"content", None, False,
				max_retries=3,
				timeout_seconds=120
			)

		assert "120 second timeout" in str(exc_info.value)
		assert "3 attempts" in str(exc_info.value)


@pytest.mark.asyncio
async def test_call_gemini_api_retries_on_timeout(generation_service, valid_transcript):
	"""Test _call_gemini_api retries on timeout and succeeds on final attempt."""
	call_count = 0

	async def mock_wait_for(coro, timeout):
		nonlocal call_count
		call_count += 1
		if call_count < 3:
			# Cancel the coroutine to avoid ResourceWarning
			coro.close()
			raise asyncio.TimeoutError
		# On 3rd attempt, consume the coroutine
		return await coro

	with patch('src.services.script_generation_service.asyncio.wait_for', side_effect=mock_wait_for), \
		 patch('src.services.script_generation_service.asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
		 patch.object(generation_service, '_call_gemini_sync', return_value=valid_transcript):

		result = await generation_service._call_gemini_api(
			"content", None, False,
			max_retries=3,
			timeout_seconds=120
		)

		assert result == valid_transcript
		# Should have slept twice (after attempt 1 and 2)
		assert mock_sleep.call_count == 2
		# Verify exponential backoff: 5s, 10s
		assert mock_sleep.call_args_list[0] == call(5)
		assert mock_sleep.call_args_list[1] == call(10)


@pytest.mark.asyncio
async def test_call_gemini_api_retries_on_exception(generation_service, valid_transcript):
	"""Test _call_gemini_api retries on generic exceptions with exponential backoff."""
	call_count = 0

	async def mock_wait_for(coro, timeout):
		nonlocal call_count
		call_count += 1
		if call_count < 3:
			coro.close()
			raise Exception("Transient API error")
		return await coro

	with patch('src.services.script_generation_service.asyncio.wait_for', side_effect=mock_wait_for), \
		 patch('src.services.script_generation_service.asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
		 patch.object(generation_service, '_call_gemini_sync', return_value=valid_transcript):

		result = await generation_service._call_gemini_api(
			"content", None, False,
			max_retries=3,
			timeout_seconds=120
		)

		assert result == valid_transcript
		assert mock_sleep.call_count == 2
		assert mock_sleep.call_args_list[0] == call(5)
		assert mock_sleep.call_args_list[1] == call(10)


@pytest.mark.asyncio
async def test_call_gemini_api_exhausted_retries_raises(generation_service):
	"""Test _call_gemini_api raises after exhausting all retries on exception."""
	async def mock_wait_for(coro, timeout):
		coro.close()
		raise Exception("Persistent API error")

	with patch('src.services.script_generation_service.asyncio.wait_for', side_effect=mock_wait_for), \
		 patch('src.services.script_generation_service.asyncio.sleep', new_callable=AsyncMock):

		with pytest.raises(Exception, match="Persistent API error"):
			await generation_service._call_gemini_api(
				"content", None, False,
				max_retries=3,
				timeout_seconds=120
			)


@pytest.mark.asyncio
async def test_generate_script_timeout_updates_episode_status(
	generation_service,
	mock_db,
	draft_episode,
	url_content_source
):
	"""Test that TimeoutError from _call_gemini_api sets episode status to failed."""
	timeout_error_msg = "Gemini API request exceeded 120 second timeout after 3 attempts"

	with patch('src.services.script_generation_service.get_episode_by_id') as mock_get_episode, \
		 patch('src.services.script_generation_service.get_content_sources') as mock_get_sources, \
		 patch('src.services.script_generation_service.update_generation_status') as mock_update_status, \
		 patch.object(generation_service, '_call_gemini_api', side_effect=TimeoutError(timeout_error_msg)):

		mock_get_episode.return_value = draft_episode
		mock_get_sources.return_value = ([url_content_source], 1)

		result = await generation_service.generate_script(mock_db, draft_episode.id)

		assert result.success is False
		assert "timeout" in result.error_message.lower()

		# Verify last status is 'failed' with error_message
		final_call = mock_update_status.call_args_list[-1]
		assert final_call[0][2] == 'failed'
		assert 'error_message' in final_call[0][3]
		assert "timeout" in final_call[0][3]['error_message'].lower()


@pytest.mark.asyncio
async def test_call_gemini_api_uses_settings_defaults(generation_service, valid_transcript):
	"""Test _call_gemini_api uses settings for default timeout and max_retries."""
	with patch('src.services.script_generation_service.asyncio.wait_for') as mock_wait_for, \
		 patch.object(generation_service, '_call_gemini_sync', return_value=valid_transcript), \
		 patch('src.services.script_generation_service.settings') as mock_settings:

		mock_settings.GEMINI_API_TIMEOUT = 60
		mock_settings.GEMINI_API_MAX_RETRIES = 2
		mock_wait_for.return_value = valid_transcript

		await generation_service._call_gemini_api("content", None, False)

		# Verify wait_for was called with the timeout from settings
		mock_wait_for.assert_called_once()
		assert mock_wait_for.call_args[1]['timeout'] == 60


def test_gemini_settings_defaults():
	"""Test that GEMINI_API_TIMEOUT and GEMINI_API_MAX_RETRIES have correct defaults."""
	from src.config import Settings
	# Use model_fields to check defaults without instantiating (avoids requiring env vars)
	fields = Settings.model_fields
	assert fields['GEMINI_API_TIMEOUT'].default == 120
	assert fields['GEMINI_API_MAX_RETRIES'].default == 3
