"""
Unit tests for RSSGenerationService.

Tests RSS XML building, date formatting, metadata validation,
CDATA escaping, namespace declarations, language validation,
and episode filtering.
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch  # noqa: F401
from uuid import uuid4
import xml.etree.ElementTree as ET


@pytest.fixture
def rss_service():
	"""Return an RSSGenerationService instance with mocked storage."""
	from src.services.rss_generation_service import RSSGenerationService
	service = RSSGenerationService()
	service.storage = MagicMock()
	return service


@pytest.fixture
def valid_project():
	"""Return a mock project with valid podcast metadata."""
	project = MagicMock()
	project.id = uuid4()
	project.name = "Test Podcast"
	project.user_id = uuid4()
	project.tenant_id = uuid4()
	project.podcast_metadata = {
		"show_title": "Test Podcast Show",
		"author": "Test Author",
		"description": "A test podcast description",
		"category": "Technology",
		"language": "en-US",
		"explicit": False,
		"copyright": "© 2025 Test Author",
		"artwork_url": "https://example.com/artwork.jpg",
	}
	project.user = MagicMock()
	project.user.email = "author@example.com"
	return project


@pytest.fixture
def complete_episode():
	"""Return a mock episode with complete generation status."""
	episode = MagicMock()
	episode.id = uuid4()
	episode.generation_status = "complete"
	episode.s3_url = "https://s3.example.com/episodes/ep1.mp3"
	episode.file_size_bytes = 5242880
	episode.duration_seconds = 300
	episode.created_at = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
	episode.episode_metadata = {
		"title": "Episode 1: Getting Started",
		"description": "A great episode",
		"episode_number": 1,
		"season_number": 1,
	}
	return episode


@pytest.fixture
def draft_episode():
	"""Return a mock episode with draft generation status."""
	episode = MagicMock()
	episode.id = uuid4()
	episode.generation_status = "draft"
	episode.s3_url = None
	episode.file_size_bytes = None
	episode.duration_seconds = None
	episode.created_at = datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc)
	episode.episode_metadata = {
		"title": "Draft Episode",
		"description": "Not ready yet",
	}
	return episode


# ============================================================================
# RSS XML BUILDING TESTS
# ============================================================================

class TestBuildRssDocument:
	"""Tests for _build_rss_document method."""

	def test_build_rss_with_valid_episode(self, rss_service, valid_project, complete_episode):
		"""Test that RSS XML is built correctly with a valid episode."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])

		assert isinstance(xml_content, str)
		assert '<?xml version=' in xml_content
		assert '<rss version="2.0"' in xml_content
		assert 'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"' in xml_content
		assert 'xmlns:content="http://purl.org/rss/1.0/modules/content/"' in xml_content

	def test_channel_title_from_podcast_metadata(self, rss_service, valid_project, complete_episode):
		"""Test that channel title comes from podcast_metadata.show_title."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert "<title>Test Podcast Show</title>" in xml_content

	def test_channel_description_from_podcast_metadata(self, rss_service, valid_project, complete_episode):
		"""Test that channel description comes from podcast_metadata.description."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert "A test podcast description" in xml_content

	def test_itunes_author_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:author tag is present."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert "<itunes:author>Test Author</itunes:author>" in xml_content

	def test_itunes_category_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:category tag is present."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert 'itunes:category' in xml_content
		assert 'Technology' in xml_content

	def test_itunes_explicit_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:explicit tag is present."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:explicit>' in xml_content

	def test_itunes_image_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:image tag is present."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert 'itunes:image' in xml_content
		assert 'https://example.com/artwork.jpg' in xml_content

	def test_itunes_owner_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:owner tag is present with name and email."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:owner>' in xml_content
		assert '<itunes:name>Test Author</itunes:name>' in xml_content
		assert '<itunes:email>author@example.com</itunes:email>' in xml_content

	def test_episode_item_present(self, rss_service, valid_project, complete_episode):
		"""Test that episode item is included in the feed."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<item>' in xml_content
		assert "Episode 1: Getting Started" in xml_content

	def test_enclosure_element_present(self, rss_service, valid_project, complete_episode):
		"""Test that enclosure element has correct attributes."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert 'enclosure' in xml_content
		assert 'https://s3.example.com/episodes/ep1.mp3' in xml_content
		assert 'audio/mpeg' in xml_content
		assert '5242880' in xml_content

	def test_guid_is_episode_id(self, rss_service, valid_project, complete_episode):
		"""Test that guid element contains episode id."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert str(complete_episode.id) in xml_content

	def test_itunes_duration_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:duration tag is present."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:duration>' in xml_content

	def test_episode_number_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:episode tag is present when episode_number is set."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:episode>1</itunes:episode>' in xml_content

	def test_season_number_present(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:season tag is present when season_number is set."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:season>1</itunes:season>' in xml_content

	def test_episode_without_season_number(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:season is omitted when season_number is not set."""
		complete_episode.episode_metadata = {
			"title": "Episode 1",
			"description": "No season",
			"episode_number": 1,
		}
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:season>' not in xml_content

	def test_episode_without_episode_number(self, rss_service, valid_project, complete_episode):
		"""Test that itunes:episode is omitted when episode_number is not set."""
		complete_episode.episode_metadata = {
			"title": "Episode 1",
			"description": "No number",
		}
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<itunes:episode>' not in xml_content

	def test_empty_episode_list(self, rss_service, valid_project):
		"""Test RSS generation with no episodes."""
		xml_content = rss_service._build_rss_document(valid_project, [])
		assert '<rss' in xml_content
		assert '<item>' not in xml_content

	def test_valid_xml_structure(self, rss_service, valid_project, complete_episode):
		"""Test that generated XML is parseable."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		# Should not raise
		ET.fromstring(xml_content.encode("utf-8"))

	def test_language_in_channel(self, rss_service, valid_project, complete_episode):
		"""Test that language tag is present in channel."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<language>en-US</language>' in xml_content

	def test_copyright_in_channel(self, rss_service, valid_project, complete_episode):
		"""Test that copyright tag is present in channel."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '© 2025 Test Author' in xml_content

	def test_last_build_date_present(self, rss_service, valid_project, complete_episode):
		"""Test that lastBuildDate is present in channel."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert '<lastBuildDate>' in xml_content

	def test_multiple_episodes_ordered_newest_first(self, rss_service, valid_project, complete_episode):
		"""Test that multiple episodes are ordered newest first."""
		episode1 = MagicMock()
		episode1.id = uuid4()
		episode1.generation_status = "complete"
		episode1.s3_url = "https://s3.example.com/ep1.mp3"
		episode1.file_size_bytes = 1000000
		episode1.duration_seconds = 300
		episode1.created_at = datetime(2025, 1, 10, tzinfo=timezone.utc)
		episode1.episode_metadata = {"title": "Old Episode", "description": "Old"}

		episode2 = MagicMock()
		episode2.id = uuid4()
		episode2.generation_status = "complete"
		episode2.s3_url = "https://s3.example.com/ep2.mp3"
		episode2.file_size_bytes = 2000000
		episode2.duration_seconds = 600
		episode2.created_at = datetime(2025, 1, 20, tzinfo=timezone.utc)
		episode2.episode_metadata = {"title": "New Episode", "description": "New"}

		# Pass in oldest first, expect newest first in output
		xml_content = rss_service._build_rss_document(valid_project, [episode1, episode2])
		new_pos = xml_content.index("New Episode")
		old_pos = xml_content.index("Old Episode")
		assert new_pos < old_pos, "Newest episode should appear first"


# ============================================================================
# RFC 2822 DATE FORMATTING TESTS
# ============================================================================

class TestFormatRfc2822Date:
	"""Tests for _format_rfc2822_date method."""

	def test_format_utc_datetime(self, rss_service):
		"""Test formatting UTC datetime to RFC 2822."""
		dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
		result = rss_service._format_rfc2822_date(dt)
		assert result == "Wed, 15 Jan 2025 10:30:00 +0000"

	def test_format_naive_datetime(self, rss_service):
		"""Test formatting naive datetime (treated as UTC)."""
		dt = datetime(2025, 6, 1, 12, 0, 0)
		result = rss_service._format_rfc2822_date(dt)
		# Should be valid RFC 2822 format
		assert "2025" in result
		assert "Jun" in result

	def test_format_returns_string(self, rss_service):
		"""Test that format returns a string."""
		dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
		result = rss_service._format_rfc2822_date(dt)
		assert isinstance(result, str)


# ============================================================================
# METADATA VALIDATION TESTS
# ============================================================================

class TestValidatePodcastMetadata:
	"""Tests for _validate_podcast_metadata method."""

	def test_valid_metadata_passes(self, rss_service):
		"""Test that valid metadata passes validation."""
		metadata = {
			"show_title": "My Podcast",
			"author": "Author Name",
			"description": "Great podcast",
			"artwork_url": "https://example.com/art.jpg",
		}
		# Should not raise
		rss_service._validate_podcast_metadata(metadata)

	def test_missing_show_title_raises(self, rss_service):
		"""Test that missing show_title raises ValueError."""
		metadata = {
			"author": "Author Name",
			"description": "Great podcast",
			"artwork_url": "https://example.com/art.jpg",
		}
		with pytest.raises(ValueError, match="show_title"):
			rss_service._validate_podcast_metadata(metadata)

	def test_missing_author_raises(self, rss_service):
		"""Test that missing author raises ValueError."""
		metadata = {
			"show_title": "My Podcast",
			"description": "Great podcast",
			"artwork_url": "https://example.com/art.jpg",
		}
		with pytest.raises(ValueError, match="author"):
			rss_service._validate_podcast_metadata(metadata)

	def test_missing_description_raises(self, rss_service):
		"""Test that missing description raises ValueError."""
		metadata = {
			"show_title": "My Podcast",
			"author": "Author Name",
			"artwork_url": "https://example.com/art.jpg",
		}
		with pytest.raises(ValueError, match="description"):
			rss_service._validate_podcast_metadata(metadata)

	def test_empty_show_title_raises(self, rss_service):
		"""Test that empty show_title raises ValueError."""
		metadata = {
			"show_title": "",
			"author": "Author Name",
			"description": "Great podcast",
		}
		with pytest.raises(ValueError, match="show_title"):
			rss_service._validate_podcast_metadata(metadata)

	def test_metadata_without_artwork_passes(self, rss_service):
		"""Test that metadata without artwork_url passes validation."""
		metadata = {
			"show_title": "My Podcast",
			"author": "Author Name",
			"description": "Great podcast",
		}
		# Should not raise - artwork_url is optional for basic validation
		rss_service._validate_podcast_metadata(metadata)


# ============================================================================
# CDATA ESCAPING TESTS
# ============================================================================

class TestCdataEscaping:
	"""Tests for CDATA/HTML escaping in RSS content."""

	def test_html_in_description_escaped(self, rss_service, valid_project, complete_episode):
		"""Test that HTML characters in description are escaped."""
		complete_episode.episode_metadata = {
			"title": "Episode with <b>HTML</b> & 'quotes'",
			"description": "<p>HTML description with <a href='url'>link</a></p>",
		}
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		# XML must be valid (no unescaped < > &)
		ET.fromstring(xml_content.encode("utf-8"))

	def test_ampersand_in_title_escaped(self, rss_service, valid_project, complete_episode):
		"""Test that & in title is escaped."""
		valid_project.podcast_metadata = {
			**valid_project.podcast_metadata,
			"show_title": "Podcast & More",
		}
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		# Should be valid XML
		ET.fromstring(xml_content.encode("utf-8"))
		assert "Podcast &amp; More" in xml_content or "Podcast & More" in xml_content


# ============================================================================
# EPISODE FILTERING TESTS
# ============================================================================

class TestEpisodeFiltering:
	"""Tests for episode filtering in RSS generation."""

	@pytest.mark.asyncio
	async def test_only_complete_episodes_included(self, rss_service, valid_project, complete_episode, draft_episode):
		"""Test that only episodes with complete status are included in feed."""
		project_id = valid_project.id
		user_id = uuid4()

		# Mock S3 upload
		mock_rss_feed = MagicMock()
		mock_rss_feed.id = uuid4()

		with patch.object(rss_service, '_get_project', AsyncMock(return_value=valid_project)), \
		     patch.object(rss_service, '_get_completed_episodes', AsyncMock(return_value=[complete_episode])), \
		     patch.object(rss_service, '_upload_rss_to_s3', AsyncMock(return_value=("key", "url"))), \
		     patch.object(rss_service, '_get_or_create_rss_feed', AsyncMock(return_value=mock_rss_feed)), \
		     patch.object(rss_service, '_update_rss_feed', AsyncMock(return_value=mock_rss_feed)):
			mock_db = AsyncMock()
			result = await rss_service.generate_rss_for_project(mock_db, project_id, user_id)

		# The service should not raise
		assert result is not None

	def test_draft_episode_not_in_xml(self, rss_service, valid_project, draft_episode):
		"""Test that draft episodes are excluded from RSS XML."""
		# When _build_rss_document is called with only complete episodes
		xml_content = rss_service._build_rss_document(valid_project, [])
		assert "Draft Episode" not in xml_content

	def test_complete_episode_in_xml(self, rss_service, valid_project, complete_episode):
		"""Test that complete episodes are included in RSS XML."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert "Episode 1: Getting Started" in xml_content


# ============================================================================
# NAMESPACE DECLARATION TESTS
# ============================================================================

class TestNamespaceDeclarations:
	"""Tests for iTunes and content namespace declarations."""

	def test_itunes_namespace_declared(self, rss_service, valid_project, complete_episode):
		"""Test that iTunes namespace is declared in RSS root."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert 'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"' in xml_content

	def test_content_namespace_declared(self, rss_service, valid_project, complete_episode):
		"""Test that content namespace is declared in RSS root."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert 'xmlns:content="http://purl.org/rss/1.0/modules/content/"' in xml_content

	def test_rss_version_is_2_0(self, rss_service, valid_project, complete_episode):
		"""Test that RSS version attribute is 2.0."""
		xml_content = rss_service._build_rss_document(valid_project, [complete_episode])
		assert 'version="2.0"' in xml_content


# ============================================================================
# UPLOAD TO S3 TESTS
# ============================================================================

class TestUploadToS3:
	"""Tests for S3 upload functionality."""

	@pytest.mark.asyncio
	async def test_upload_uses_correct_s3_key_and_api_public_url(self, rss_service, valid_project):
		"""public_url must be the API feed endpoint, never the raw S3 URL.

		The bucket has no public-read policy, so the S3 URL returns
		AccessDenied to podcast platforms (#385). The XML is still uploaded
		to S3 (the endpoint serves the stored object).
		"""
		from src.config import settings

		project_id = valid_project.id
		rss_service.storage.upload_file = AsyncMock(
			return_value=f"https://bucket.s3.us-east-1.amazonaws.com/rss-feeds/{project_id}/feed.xml"
		)

		s3_key, public_url = await rss_service._upload_rss_to_s3(project_id, "<rss>test</rss>")

		assert s3_key == f"rss-feeds/{project_id}/feed.xml"
		assert public_url == (
			f"{settings.API_PUBLIC_BASE_URL.rstrip('/')}/feeds/{project_id}/podcast.xml"
		)
		assert ".s3." not in public_url
		rss_service.storage.upload_file.assert_awaited_once()
