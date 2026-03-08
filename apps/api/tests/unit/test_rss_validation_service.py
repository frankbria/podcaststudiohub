"""
Unit tests for RSSValidationService.

Tests Apple Podcasts, Spotify, and Google Podcasts validation,
image validation, date parsing, GUID uniqueness, and field checks.
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import xml.etree.ElementTree as ET

from src.services.rss_validation_service import RSSValidationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>A great podcast</description>
    <language>en-US</language>
    <lastBuildDate>Wed, 15 Jan 2025 10:30:00 +0000</lastBuildDate>
    <itunes:author>Test Author</itunes:author>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:image href="https://example.com/art.jpg"/>
    <item>
      <title>Episode 1</title>
      <description>Great episode</description>
      <pubDate>Wed, 15 Jan 2025 10:30:00 +0000</pubDate>
      <enclosure url="https://s3.example.com/ep1.mp3" length="5000000" type="audio/mpeg"/>
      <guid isPermaLink="false">episode-guid-001</guid>
      <itunes:duration>1800</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def service():
	"""Return RSSValidationService with image validation mocked out."""
	svc = RSSValidationService()
	return svc


@pytest.fixture
def service_no_image():
	"""Return RSSValidationService with _validate_image always returning []."""
	svc = RSSValidationService()
	svc._validate_image = AsyncMock(return_value=[])
	return svc


# ---------------------------------------------------------------------------
# _parse_rss_xml
# ---------------------------------------------------------------------------

def test_parse_rss_xml_valid(service):
	root = service._parse_rss_xml(VALID_RSS)
	assert root.tag == "rss"
	assert root.find("channel") is not None


def test_parse_rss_xml_invalid(service):
	with pytest.raises(ValueError, match="Invalid RSS XML"):
		service._parse_rss_xml("<not-valid-xml")


# ---------------------------------------------------------------------------
# _is_valid_rfc2822_date
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("date_str,expected", [
	("Wed, 15 Jan 2025 10:30:00 +0000", True),
	("Mon, 01 Dec 2025 00:00:00 GMT", True),
	("not-a-date", False),
	("", False),
	(None, False),
])
def test_is_valid_rfc2822_date(service, date_str, expected):
	assert service._is_valid_rfc2822_date(date_str) == expected


# ---------------------------------------------------------------------------
# _is_valid_language_code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang,expected", [
	("en", True),
	("en-US", True),
	("zh-Hant-TW", True),
	("fr-FR", True),
	("invalid lang", False),
	("123", False),
	("", False),
])
def test_is_valid_language_code(service, lang, expected):
	assert service._is_valid_language_code(lang) == expected


# ---------------------------------------------------------------------------
# Apple Podcasts validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apple_valid_feed(service_no_image):
	root = service_no_image._parse_rss_xml(VALID_RSS)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.directory == "apple_podcasts"
	assert result.valid is True
	assert result.errors == []


@pytest.mark.asyncio
async def test_apple_missing_itunes_author(service_no_image):
	rss = VALID_RSS.replace("<itunes:author>Test Author</itunes:author>", "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	fields = [e.field for e in result.errors]
	assert "itunes:author" in fields


@pytest.mark.asyncio
async def test_apple_missing_itunes_image(service_no_image):
	rss = VALID_RSS.replace('<itunes:image href="https://example.com/art.jpg"/>', "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	fields = [e.field for e in result.errors]
	assert "itunes:image" in fields


@pytest.mark.asyncio
async def test_apple_missing_itunes_category(service_no_image):
	rss = VALID_RSS.replace('<itunes:category text="Technology"/>', "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "itunes:category" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_missing_itunes_explicit(service_no_image):
	rss = VALID_RSS.replace(
		"<itunes:explicit>false</itunes:explicit>",
		"",
		1,  # only replace channel-level, not item-level
	)
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "itunes:explicit" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_episode_invalid_audio_type(service_no_image):
	rss = VALID_RSS.replace('type="audio/mpeg"', 'type="audio/x-weird"')
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "item/enclosure/@type" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_episode_missing_duration(service_no_image):
	rss = VALID_RSS.replace("<itunes:duration>1800</itunes:duration>", "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "item/itunes:duration" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_episode_missing_pub_date(service_no_image):
	rss = VALID_RSS.replace(
		"<pubDate>Wed, 15 Jan 2025 10:30:00 +0000</pubDate>", ""
	)
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "item/pubDate" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_episode_invalid_pub_date(service_no_image):
	rss = VALID_RSS.replace(
		"<pubDate>Wed, 15 Jan 2025 10:30:00 +0000</pubDate>",
		"<pubDate>not-a-date</pubDate>",
	)
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "item/pubDate" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_episode_missing_guid(service_no_image):
	rss = VALID_RSS.replace('<guid isPermaLink="false">episode-guid-001</guid>', "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "item/guid" for e in result.errors)


@pytest.mark.asyncio
async def test_apple_episode_warning_for_missing_episode_type(service_no_image):
	rss = VALID_RSS.replace("<itunes:episodeType>full</itunes:episodeType>", "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_apple_podcasts(root, now)

	# Should be a warning, not an error
	assert result.valid is True
	assert any(w.field == "item/itunes:episodeType" for w in result.warnings)


# ---------------------------------------------------------------------------
# Spotify validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_valid_feed(service_no_image):
	root = service_no_image._parse_rss_xml(VALID_RSS)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_spotify(root, now)

	assert result.directory == "spotify"
	assert result.valid is True
	assert result.errors == []


@pytest.mark.asyncio
async def test_spotify_rejects_non_mpeg_audio(service_no_image):
	rss = VALID_RSS.replace('type="audio/mpeg"', 'type="audio/x-m4a"')
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_spotify(root, now)

	assert result.valid is False
	assert any(e.field == "item/enclosure/@type" for e in result.errors)


@pytest.mark.asyncio
async def test_spotify_detects_duplicate_guids(service_no_image):
	rss_with_dupe = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>A podcast</description>
    <language>en-US</language>
    <itunes:image href="https://example.com/art.jpg"/>
    <item>
      <title>Episode 1</title>
      <description>Ep 1</description>
      <pubDate>Wed, 15 Jan 2025 10:30:00 +0000</pubDate>
      <enclosure url="https://s3.example.com/ep1.mp3" length="5000000" type="audio/mpeg"/>
      <guid>same-guid</guid>
    </item>
    <item>
      <title>Episode 2</title>
      <description>Ep 2</description>
      <pubDate>Thu, 16 Jan 2025 10:30:00 +0000</pubDate>
      <enclosure url="https://s3.example.com/ep2.mp3" length="5000000" type="audio/mpeg"/>
      <guid>same-guid</guid>
    </item>
  </channel>
</rss>"""
	root = service_no_image._parse_rss_xml(rss_with_dupe)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_spotify(root, now)

	assert result.valid is False
	assert any(e.field == "item/guid" for e in result.errors)


@pytest.mark.asyncio
async def test_spotify_missing_language(service_no_image):
	rss = VALID_RSS.replace("<language>en-US</language>", "")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_spotify(root, now)

	assert result.valid is False
	assert any(e.field == "language" for e in result.errors)


@pytest.mark.asyncio
async def test_spotify_missing_enclosure_length(service_no_image):
	rss = VALID_RSS.replace('length="5000000"', 'length="notanumber"')
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_spotify(root, now)

	assert result.valid is False
	assert any(e.field == "item/enclosure/@length" for e in result.errors)


# ---------------------------------------------------------------------------
# Google Podcasts validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_valid_feed(service_no_image):
	root = service_no_image._parse_rss_xml(VALID_RSS)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_google_podcasts(root, now)

	assert result.directory == "google_podcasts"
	assert result.valid is True
	assert result.errors == []


@pytest.mark.asyncio
async def test_google_missing_last_build_date(service_no_image):
	rss = VALID_RSS.replace(
		"<lastBuildDate>Wed, 15 Jan 2025 10:30:00 +0000</lastBuildDate>", ""
	)
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_google_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "lastBuildDate" for e in result.errors)


@pytest.mark.asyncio
async def test_google_invalid_last_build_date(service_no_image):
	rss = VALID_RSS.replace(
		"<lastBuildDate>Wed, 15 Jan 2025 10:30:00 +0000</lastBuildDate>",
		"<lastBuildDate>not-a-date</lastBuildDate>",
	)
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_google_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "lastBuildDate" for e in result.errors)


@pytest.mark.asyncio
async def test_google_invalid_language_code(service_no_image):
	rss = VALID_RSS.replace("<language>en-US</language>", "<language>123-invalid lang</language>")
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_google_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "language" for e in result.errors)


@pytest.mark.asyncio
async def test_google_missing_episode_enclosure(service_no_image):
	rss = VALID_RSS.replace(
		'<enclosure url="https://s3.example.com/ep1.mp3" length="5000000" type="audio/mpeg"/>',
		"",
	)
	root = service_no_image._parse_rss_xml(rss)
	now = datetime.now(timezone.utc)
	result = await service_no_image._validate_google_podcasts(root, now)

	assert result.valid is False
	assert any(e.field == "item/enclosure" for e in result.errors)


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_validation_success():
	"""Valid image URL returns no errors."""
	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.headers = {
		"content-type": "image/jpeg",
		"content-length": "102400",  # 100 KB
	}

	mock_client = AsyncMock()
	mock_client.head = AsyncMock(return_value=mock_response)
	# Prevent dimension check from running by making GET fail gracefully
	mock_client.get = AsyncMock(side_effect=Exception("skip"))

	svc = RSSValidationService(http_client=mock_client)
	errors = await svc._validate_image("https://example.com/art.jpg", min_dimension=3000)
	assert errors == []


@pytest.mark.asyncio
async def test_image_validation_not_accessible():
	"""Non-200 response is reported as an error."""
	mock_response = MagicMock()
	mock_response.status_code = 404
	mock_response.headers = {}

	mock_client = AsyncMock()
	mock_client.head = AsyncMock(return_value=mock_response)

	svc = RSSValidationService(http_client=mock_client)
	errors = await svc._validate_image("https://example.com/missing.jpg")
	assert len(errors) == 1
	assert errors[0].level == "error"
	assert "404" in errors[0].message


@pytest.mark.asyncio
async def test_image_validation_wrong_format():
	"""Non-image content type is flagged."""
	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.headers = {
		"content-type": "image/gif",
		"content-length": "50000",
	}

	mock_client = AsyncMock()
	mock_client.head = AsyncMock(return_value=mock_response)
	mock_client.get = AsyncMock(side_effect=Exception("skip"))

	svc = RSSValidationService(http_client=mock_client)
	errors = await svc._validate_image("https://example.com/art.gif")
	assert any("JPG or PNG" in e.message for e in errors)


@pytest.mark.asyncio
async def test_image_validation_too_large():
	"""File size over 500 KB is reported."""
	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.headers = {
		"content-type": "image/jpeg",
		"content-length": str(600 * 1024),  # 600 KB
	}

	mock_client = AsyncMock()
	mock_client.head = AsyncMock(return_value=mock_response)
	mock_client.get = AsyncMock(side_effect=Exception("skip"))

	svc = RSSValidationService(http_client=mock_client)
	errors = await svc._validate_image("https://example.com/big.jpg", max_size_kb=500)
	assert any("500 KB" in e.message for e in errors)


@pytest.mark.asyncio
async def test_image_validation_timeout():
	"""Timeout is reported as an error."""
	import httpx

	mock_client = AsyncMock()
	mock_client.head = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

	svc = RSSValidationService(http_client=mock_client)
	errors = await svc._validate_image("https://example.com/slow.jpg")
	assert len(errors) == 1
	assert "timed out" in errors[0].message.lower()


# ---------------------------------------------------------------------------
# validate_rss_feed (full flow, mocked DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_rss_feed_full_flow():
	"""Full validation flow stores results to DB and returns correct structure."""
	mock_db = AsyncMock()
	mock_rss_feed = MagicMock()
	mock_rss_feed.validation_status = {}

	mock_result = MagicMock()
	mock_result.scalar_one_or_none = MagicMock(return_value=mock_rss_feed)
	mock_db.execute = AsyncMock(return_value=mock_result)
	mock_db.commit = AsyncMock()

	svc = RSSValidationService()
	svc._validate_image = AsyncMock(return_value=[])

	result = await svc.validate_rss_feed(
		db=mock_db,
		project_id=uuid4(),
		rss_content=VALID_RSS,
	)

	assert result.apple_podcasts.directory == "apple_podcasts"
	assert result.spotify.directory == "spotify"
	assert result.google_podcasts.directory == "google_podcasts"
	assert isinstance(result.is_valid_for_all, bool)
	assert mock_db.commit.called


@pytest.mark.asyncio
async def test_validate_rss_feed_raises_on_missing_content():
	"""Raises ValueError when rss_content is empty."""
	svc = RSSValidationService()
	mock_db = AsyncMock()

	with pytest.raises(ValueError, match="rss_content is required"):
		await svc.validate_rss_feed(db=mock_db, project_id=uuid4(), rss_content=None)


@pytest.mark.asyncio
async def test_validate_rss_feed_raises_on_bad_xml():
	"""Raises ValueError when RSS XML is malformed."""
	svc = RSSValidationService()
	mock_db = AsyncMock()

	with pytest.raises(ValueError, match="Invalid RSS XML"):
		await svc.validate_rss_feed(db=mock_db, project_id=uuid4(), rss_content="<broken")


# ---------------------------------------------------------------------------
# get_validation_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_validation_status_returns_none_when_no_feed():
	"""Returns None when no RSSFeed record exists."""
	mock_db = AsyncMock()
	mock_result = MagicMock()
	mock_result.scalar_one_or_none = MagicMock(return_value=None)
	mock_db.execute = AsyncMock(return_value=mock_result)

	svc = RSSValidationService()
	result = await svc.get_validation_status(mock_db, uuid4())
	assert result is None


@pytest.mark.asyncio
async def test_get_validation_status_returns_none_when_empty_status():
	"""Returns None when validation_status is empty dict."""
	mock_db = AsyncMock()
	mock_feed = MagicMock()
	mock_feed.validation_status = {}

	mock_result = MagicMock()
	mock_result.scalar_one_or_none = MagicMock(return_value=mock_feed)
	mock_db.execute = AsyncMock(return_value=mock_result)

	svc = RSSValidationService()
	result = await svc.get_validation_status(mock_db, uuid4())
	assert result is None
