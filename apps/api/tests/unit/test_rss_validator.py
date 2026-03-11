"""
Unit tests for RSSValidatorService.

Tests validation logic for Apple Podcasts, Spotify, and Google Podcasts standards.
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from src.services.rss_validator import RSSValidatorService, _parse_duration


# ============================================================================
# SAMPLE RSS XML FIXTURES
# ============================================================================

VALID_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Test Podcast</title>
    <link>https://example.com</link>
    <description>A test podcast for validation</description>
    <language>en-us</language>
    <itunes:author>Test Author</itunes:author>
    <itunes:owner>
      <itunes:name>Test Author</itunes:name>
      <itunes:email>author@example.com</itunes:email>
    </itunes:owner>
    <itunes:image href="https://example.com/artwork.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <item>
      <title>Episode 1</title>
      <description>First episode</description>
      <pubDate>Wed, 15 Jan 2025 10:00:00 +0000</pubDate>
      <enclosure url="https://example.com/ep1.mp3" length="5242880" type="audio/mpeg"/>
      <guid isPermaLink="false">episode-1-guid</guid>
      <itunes:duration>300</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>
  </channel>
</rss>"""

MINIMAL_CHANNEL_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Minimal Podcast</title>
    <description>Just a minimal feed</description>
  </channel>
</rss>"""

INVALID_XML = "this is not xml at all <unclosed"

EMPTY_CHANNEL_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
  </channel>
</rss>"""


@pytest.fixture
def validator():
	"""Return an RSSValidatorService instance."""
	return RSSValidatorService()


# ============================================================================
# TOP-LEVEL validate_feed TESTS
# ============================================================================

class TestValidateFeed:
	"""Tests for the top-level validate_feed method."""

	def test_validate_returns_all_platforms(self, validator):
		"""Test that validate_feed returns results for all three platforms."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert "apple_podcasts" in result
		assert "spotify" in result
		assert "google_podcasts" in result

	def test_validate_returns_timestamp(self, validator):
		"""Test that validate_feed includes last_validated_at timestamp."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert "last_validated_at" in result
		assert result["last_validated_at"] is not None

	def test_validate_valid_feed_passes_all(self, validator):
		"""Test that a well-formed feed passes all platform validations."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert result["apple_podcasts"]["valid"] is True
		assert result["spotify"]["valid"] is True
		assert result["google_podcasts"]["valid"] is True

	def test_validate_errors_are_lists(self, validator):
		"""Test that error fields are always lists."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert isinstance(result["apple_podcasts"]["errors"], list)
		assert isinstance(result["spotify"]["errors"], list)
		assert isinstance(result["google_podcasts"]["errors"], list)


# ============================================================================
# APPLE PODCASTS VALIDATION TESTS
# ============================================================================

class TestApplePodcastsValidation:
	"""Tests for Apple Podcasts specific validation rules."""

	def test_valid_feed_passes(self, validator):
		"""Test that a compliant feed passes Apple Podcasts validation."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert result["apple_podcasts"]["valid"] is True
		assert result["apple_podcasts"]["errors"] == []

	def test_missing_title_fails(self, validator):
		"""Test that missing channel title fails Apple Podcasts validation."""
		result = validator.validate_feed(EMPTY_CHANNEL_RSS)
		assert result["apple_podcasts"]["valid"] is False
		errors_str = " ".join(result["apple_podcasts"]["errors"])
		assert "title" in errors_str.lower()

	def test_missing_description_fails(self, validator):
		"""Test that missing description fails Apple Podcasts validation."""
		result = validator.validate_feed(EMPTY_CHANNEL_RSS)
		assert result["apple_podcasts"]["valid"] is False
		errors_str = " ".join(result["apple_podcasts"]["errors"])
		assert "description" in errors_str.lower()

	def test_missing_itunes_author_fails(self, validator):
		"""Test that missing itunes:author is flagged."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test</title>
    <link>https://example.com</link>
    <description>Test desc</description>
    <language>en-us</language>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["apple_podcasts"]["valid"] is False
		errors_str = " ".join(result["apple_podcasts"]["errors"])
		assert "author" in errors_str.lower()

	def test_episode_missing_enclosure_fails(self, validator):
		"""Test that episode without enclosure fails Apple Podcasts validation."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test</title>
    <link>https://example.com</link>
    <description>Test</description>
    <language>en-us</language>
    <itunes:author>Author</itunes:author>
    <itunes:owner>
      <itunes:name>Author</itunes:name>
      <itunes:email>a@b.com</itunes:email>
    </itunes:owner>
    <itunes:image href="https://example.com/art.jpg"/>
    <itunes:category text="Technology"/>
    <item>
      <title>Episode 1</title>
      <pubDate>Wed, 15 Jan 2025 10:00:00 +0000</pubDate>
      <guid>ep1</guid>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["apple_podcasts"]["valid"] is False
		errors_str = " ".join(result["apple_podcasts"]["errors"])
		assert "enclosure" in errors_str.lower()

	def test_no_episodes_is_valid(self, validator):
		"""Test that a feed with no episodes can still pass channel-level validation."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Empty Podcast</title>
    <link>https://example.com</link>
    <description>No episodes yet</description>
    <language>en-us</language>
    <itunes:author>Author</itunes:author>
    <itunes:owner>
      <itunes:name>Author</itunes:name>
      <itunes:email>a@b.com</itunes:email>
    </itunes:owner>
    <itunes:image href="https://example.com/art.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["apple_podcasts"]["valid"] is True


# ============================================================================
# SPOTIFY VALIDATION TESTS
# ============================================================================

class TestSpotifyValidation:
	"""Tests for Spotify specific validation rules."""

	def test_valid_feed_passes(self, validator):
		"""Test that a compliant feed passes Spotify validation."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert result["spotify"]["valid"] is True

	def test_unsupported_audio_type_flagged(self, validator):
		"""Test that unsupported audio format is flagged."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test</title>
    <item>
      <title>Episode 1</title>
      <enclosure url="https://example.com/ep1.xyz" length="1000" type="audio/xyz-unsupported"/>
      <guid>ep1</guid>
      <itunes:duration xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">300</itunes:duration>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["spotify"]["valid"] is False
		errors_str = " ".join(result["spotify"]["errors"])
		assert "unsupported" in errors_str.lower() or "audio" in errors_str.lower()

	def test_episode_too_short_flagged(self, validator):
		"""Test that episode shorter than 15 seconds is flagged."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test</title>
    <item>
      <title>Tiny Episode</title>
      <enclosure url="https://example.com/ep1.mp3" length="100" type="audio/mpeg"/>
      <guid>ep1</guid>
      <itunes:duration>5</itunes:duration>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["spotify"]["valid"] is False
		errors_str = " ".join(result["spotify"]["errors"])
		assert "minimum" in errors_str.lower() or "duration" in errors_str.lower()

	def test_episode_too_long_flagged(self, validator):
		"""Test that episode longer than 12 hours (43200s) is flagged."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Test</title>
    <item>
      <title>Very Long Episode</title>
      <enclosure url="https://example.com/ep1.mp3" length="100000" type="audio/mpeg"/>
      <guid>ep1</guid>
      <itunes:duration>50000</itunes:duration>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["spotify"]["valid"] is False
		errors_str = " ".join(result["spotify"]["errors"])
		assert "maximum" in errors_str.lower() or "duration" in errors_str.lower()

	def test_missing_enclosure_flagged(self, validator):
		"""Test that episode without enclosure fails Spotify validation."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test</title>
    <item>
      <title>Episode 1</title>
      <guid>ep1</guid>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["spotify"]["valid"] is False


# ============================================================================
# GOOGLE PODCASTS VALIDATION TESTS
# ============================================================================

class TestGooglePodcastsValidation:
	"""Tests for Google Podcasts specific validation rules."""

	def test_valid_feed_passes(self, validator):
		"""Test that a compliant feed passes Google Podcasts validation."""
		result = validator.validate_feed(VALID_RSS_XML)
		assert result["google_podcasts"]["valid"] is True

	def test_missing_title_fails(self, validator):
		"""Test that missing channel title fails Google Podcasts validation."""
		result = validator.validate_feed(EMPTY_CHANNEL_RSS)
		assert result["google_podcasts"]["valid"] is False

	def test_invalid_enclosure_url_flagged(self, validator):
		"""Test that non-HTTP enclosure URL is flagged."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test</title>
    <description>Test</description>
    <item>
      <title>Episode 1</title>
      <enclosure url="ftp://example.com/ep1.mp3" length="1000" type="audio/mpeg"/>
      <guid>ep1</guid>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["google_podcasts"]["valid"] is False
		errors_str = " ".join(result["google_podcasts"]["errors"])
		assert "url" in errors_str.lower() or "http" in errors_str.lower()

	def test_episode_without_enclosure_flagged(self, validator):
		"""Test that episodes without enclosure fail Google validation."""
		rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test</title>
    <description>Test</description>
    <item>
      <title>Episode 1</title>
      <guid>ep1</guid>
    </item>
  </channel>
</rss>"""
		result = validator.validate_feed(rss)
		assert result["google_podcasts"]["valid"] is False


# ============================================================================
# DURATION PARSING TESTS
# ============================================================================

class TestParseDuration:
	"""Tests for the _parse_duration helper function."""

	def test_parse_integer_seconds(self):
		"""Test parsing plain integer duration."""
		assert _parse_duration(300) == 300

	def test_parse_string_seconds(self):
		"""Test parsing duration as string integer."""
		assert _parse_duration("300") == 300

	def test_parse_hh_mm_ss_format(self):
		"""Test parsing HH:MM:SS duration format."""
		assert _parse_duration("1:05:30") == 3930

	def test_parse_mm_ss_format(self):
		"""Test parsing MM:SS duration format."""
		assert _parse_duration("5:30") == 330

	def test_parse_invalid_returns_none(self):
		"""Test that invalid duration returns None."""
		assert _parse_duration("not-a-duration") is None

	def test_parse_none_returns_none(self):
		"""Test that None input returns None."""
		assert _parse_duration(None) is None

	def test_parse_zero(self):
		"""Test that zero duration parses correctly."""
		assert _parse_duration(0) == 0
