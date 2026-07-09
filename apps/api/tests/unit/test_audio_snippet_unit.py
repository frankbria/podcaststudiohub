"""
Unit tests for audio snippet utilities and schemas.

These tests do not require a database connection.
"""

import pytest
from uuid import uuid4
from src.utils.datetime_utils import utcnow


# ============================================================================
# AUDIO UTILITIES
# ============================================================================

class TestValidateAudioFormat:
	"""Tests for validate_audio_format()."""

	def test_mp3_valid(self):
		from src.utils.audio_utils import validate_audio_format
		assert validate_audio_format("intro.mp3") == "mp3"

	def test_wav_valid(self):
		from src.utils.audio_utils import validate_audio_format
		assert validate_audio_format("outro.wav") == "wav"

	def test_aac_valid(self):
		from src.utils.audio_utils import validate_audio_format
		assert validate_audio_format("music.aac") == "aac"

	def test_ogg_valid(self):
		from src.utils.audio_utils import validate_audio_format
		assert validate_audio_format("sound.ogg") == "ogg"

	def test_uppercase_extension(self):
		from src.utils.audio_utils import validate_audio_format
		assert validate_audio_format("INTRO.MP3") == "mp3"

	def test_mixed_case_extension(self):
		from src.utils.audio_utils import validate_audio_format
		assert validate_audio_format("File.Wav") == "wav"

	def test_invalid_mp4_rejected(self):
		from src.utils.audio_utils import validate_audio_format
		with pytest.raises(ValueError, match="Unsupported file format"):
			validate_audio_format("video.mp4")

	def test_invalid_txt_rejected(self):
		from src.utils.audio_utils import validate_audio_format
		with pytest.raises(ValueError):
			validate_audio_format("document.txt")

	def test_invalid_exe_rejected(self):
		from src.utils.audio_utils import validate_audio_format
		with pytest.raises(ValueError):
			validate_audio_format("malware.exe")

	def test_no_extension_rejected(self):
		from src.utils.audio_utils import validate_audio_format
		with pytest.raises(ValueError):
			validate_audio_format("audio_file_no_ext")

	def test_with_valid_mime_type(self):
		from src.utils.audio_utils import validate_audio_format
		# Valid extension + valid MIME type
		assert validate_audio_format("audio.mp3", "audio/mpeg") == "mp3"

	def test_with_generic_mime_type(self):
		from src.utils.audio_utils import validate_audio_format
		# Valid extension + generic MIME type (some clients send this)
		assert validate_audio_format("audio.mp3", "application/octet-stream") == "mp3"


class TestValidateFileSize:
	"""Tests for validate_file_size()."""

	def test_valid_1mb(self):
		from src.utils.audio_utils import validate_file_size
		validate_file_size(1 * 1024 * 1024)  # Should not raise

	def test_valid_minimum_boundary(self):
		from src.utils.audio_utils import validate_file_size
		validate_file_size(100 * 1024)  # Exactly 100 KB should be valid

	def test_valid_maximum_boundary(self):
		from src.utils.audio_utils import validate_file_size
		validate_file_size(50 * 1024 * 1024)  # Exactly 50 MB should be valid

	def test_too_large_rejected(self):
		from src.utils.audio_utils import validate_file_size
		with pytest.raises(ValueError, match="too large"):
			validate_file_size(51 * 1024 * 1024)

	def test_too_small_rejected(self):
		from src.utils.audio_utils import validate_file_size
		with pytest.raises(ValueError, match="too small"):
			validate_file_size(99 * 1024)  # Just under 100 KB

	def test_empty_file_rejected(self):
		from src.utils.audio_utils import validate_file_size
		with pytest.raises(ValueError):
			validate_file_size(0)


class TestGenerateS3Key:
	"""Tests for generate_s3_key()."""

	def test_key_format(self):
		from src.utils.audio_utils import generate_s3_key
		user_id = str(uuid4())
		snippet_id = str(uuid4())
		key = generate_s3_key(user_id, snippet_id, "mp3")
		assert key == f"audio-snippets/{user_id}/{snippet_id}.mp3"

	def test_key_starts_with_prefix(self):
		from src.utils.audio_utils import generate_s3_key
		key = generate_s3_key("user123", "snippet456", "wav")
		assert key.startswith("audio-snippets/")

	def test_key_includes_extension(self):
		from src.utils.audio_utils import generate_s3_key
		key = generate_s3_key("u", "s", "aac")
		assert key.endswith(".aac")

	def test_different_formats(self):
		from src.utils.audio_utils import generate_s3_key
		for fmt in ["mp3", "wav", "aac", "ogg"]:
			key = generate_s3_key("user", "snippet", fmt)
			assert key.endswith(f".{fmt}")


class TestGetContentType:
	"""Tests for get_content_type()."""

	def test_mp3_content_type(self):
		from src.utils.audio_utils import get_content_type
		assert get_content_type("mp3") == "audio/mpeg"

	def test_wav_content_type(self):
		from src.utils.audio_utils import get_content_type
		assert get_content_type("wav") == "audio/wav"

	def test_aac_content_type(self):
		from src.utils.audio_utils import get_content_type
		assert get_content_type("aac") == "audio/aac"

	def test_ogg_content_type(self):
		from src.utils.audio_utils import get_content_type
		assert get_content_type("ogg") == "audio/ogg"

	def test_unknown_fallback(self):
		from src.utils.audio_utils import get_content_type
		assert get_content_type("xyz") == "application/octet-stream"


class TestGetFileExtension:
	"""Tests for get_file_extension()."""

	def test_mp3(self):
		from src.utils.audio_utils import get_file_extension
		assert get_file_extension("audio.mp3") == "mp3"

	def test_uppercase(self):
		from src.utils.audio_utils import get_file_extension
		assert get_file_extension("AUDIO.WAV") == "wav"

	def test_no_extension(self):
		from src.utils.audio_utils import get_file_extension
		assert get_file_extension("audio") == ""

	def test_multiple_dots(self):
		from src.utils.audio_utils import get_file_extension
		assert get_file_extension("my.audio.file.mp3") == "mp3"


# ============================================================================
# AUDIO SNIPPET SCHEMAS
# ============================================================================

class TestSnippetTypeEnum:
	"""Tests for SnippetType enum."""

	def test_all_valid_types(self):
		from src.schemas.audio_snippet import SnippetType
		assert SnippetType.intro == "intro"
		assert SnippetType.outro == "outro"
		assert SnippetType.midroll == "midroll"
		assert SnippetType.ad == "ad"
		assert SnippetType.music == "music"
		assert SnippetType.other == "other"

	def test_invalid_type(self):
		from src.schemas.audio_snippet import SnippetType
		with pytest.raises(ValueError):
			SnippetType("invalid_type")


class TestAudioSnippetUpdate:
	"""Tests for AudioSnippetUpdate schema."""

	def test_all_fields_optional(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		update = AudioSnippetUpdate()
		assert update.model_dump(exclude_unset=True) == {}

	def test_name_only(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		update = AudioSnippetUpdate(name="New Name")
		data = update.model_dump(exclude_unset=True)
		assert data == {"name": "New Name"}

	def test_description_only(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		update = AudioSnippetUpdate(description="Updated desc")
		data = update.model_dump(exclude_unset=True)
		assert data == {"description": "Updated desc"}

	def test_snippet_type_only(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate, SnippetType
		update = AudioSnippetUpdate(snippet_type=SnippetType.outro)
		data = update.model_dump(exclude_unset=True)
		assert data == {"snippet_type": SnippetType.outro}

	def test_all_fields(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate, SnippetType
		update = AudioSnippetUpdate(
			name="Name",
			description="Desc",
			snippet_type=SnippetType.midroll,
		)
		data = update.model_dump(exclude_unset=True)
		assert len(data) == 3

	def test_empty_name_rejected(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		with pytest.raises(ValueError):
			AudioSnippetUpdate(name="   ")

	def test_whitespace_only_name_rejected(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		with pytest.raises(ValueError):
			AudioSnippetUpdate(name="\t\n")

	def test_name_max_length_enforced(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		with pytest.raises(ValueError):
			AudioSnippetUpdate(name="x" * 256)  # Over 255 chars

	def test_description_max_length_enforced(self):
		from src.schemas.audio_snippet import AudioSnippetUpdate
		with pytest.raises(ValueError):
			AudioSnippetUpdate(description="x" * 501)  # Over 500 chars


class TestAudioSnippetResponse:
	"""Tests for AudioSnippetResponse schema."""

	def test_from_attributes_enabled(self):
		from src.schemas.audio_snippet import AudioSnippetResponse
		assert AudioSnippetResponse.model_config.get("from_attributes") is True

	def test_response_has_required_fields(self):
		from src.schemas.audio_snippet import AudioSnippetResponse
		response = AudioSnippetResponse(
			id=uuid4(),
			user_id=uuid4(),
			tenant_id=uuid4(),
			project_id=None,
			name="Test Snippet",
			snippet_type="intro",
			description=None,
			file_path="audio-snippets/test.mp3",
			s3_key=None,
			s3_url=None,
			duration_seconds=None,
			file_size_bytes=None,
			file_format=None,
			created_at=utcnow(),
			updated_at=utcnow(),
		)
		assert response.name == "Test Snippet"
		assert response.snippet_type == "intro"
		assert response.project_id is None


class TestAudioSnippetListResponse:
	"""Tests for AudioSnippetListResponse schema."""

	def test_pagination_fields(self):
		from src.schemas.audio_snippet import AudioSnippetListResponse
		resp = AudioSnippetListResponse(
			snippets=[],
			total=0,
			page=1,
			page_size=20,
			total_pages=0,
		)
		assert resp.total == 0
		assert resp.page == 1
		assert resp.page_size == 20
		assert resp.total_pages == 0


class TestDownloadUrlResponse:
	"""Tests for DownloadUrlResponse schema."""

	def test_default_expiry(self):
		from src.schemas.audio_snippet import DownloadUrlResponse
		resp = DownloadUrlResponse(
			snippet_id=uuid4(),
			download_url="https://example.com/presigned",
		)
		assert resp.expires_in_seconds == 3600

	def test_custom_expiry(self):
		from src.schemas.audio_snippet import DownloadUrlResponse
		resp = DownloadUrlResponse(
			snippet_id=uuid4(),
			download_url="https://example.com/presigned",
			expires_in_seconds=7200,
		)
		assert resp.expires_in_seconds == 7200
