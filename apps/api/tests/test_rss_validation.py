"""
Tests for RSS feed validation service and endpoints.

Covers:
- Service unit tests (validation logic with inline XML)
- Endpoint integration tests (HTTP layer)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from src.services.rss_validation_service import RSSValidationService
from src.schemas.rss_feed import ValidationStatusUpdate


# ---------------------------------------------------------------------------
# Helpers - RSS XML fixtures
# ---------------------------------------------------------------------------

VALID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>My Test Podcast</title>
    <link>https://example.com</link>
    <description>A great podcast about testing.</description>
    <language>en-US</language>
    <lastBuildDate>Mon, 18 Dec 2025 10:45:30 +0000</lastBuildDate>
    <itunes:author>Test Author</itunes:author>
    <itunes:image href="https://example.com/artwork.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <image>
      <url>https://example.com/artwork.jpg</url>
      <title>My Test Podcast</title>
    </image>
    <item>
      <title>Episode 1</title>
      <description>First episode description.</description>
      <pubDate>Mon, 18 Dec 2025 10:00:00 +0000</pubDate>
      <guid>urn:uuid:episode-001</guid>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="12345678"/>
      <itunes:duration>3600</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
    </item>
  </channel>
</rss>"""

MISSING_REQUIRED_FIELDS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Incomplete Podcast</title>
    <item>
      <title>Episode 1</title>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="12345678"/>
      <guid>urn:uuid:ep-001</guid>
      <pubDate>Mon, 18 Dec 2025 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

INVALID_AUDIO_MIME_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>Podcast description</description>
    <language>en</language>
    <lastBuildDate>Mon, 18 Dec 2025 10:45:30 +0000</lastBuildDate>
    <itunes:author>Author</itunes:author>
    <itunes:image href="https://example.com/artwork.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <item>
      <title>Episode 1</title>
      <description>Description</description>
      <pubDate>Mon, 18 Dec 2025 10:00:00 +0000</pubDate>
      <guid>urn:uuid:ep-001</guid>
      <enclosure url="https://example.com/ep1.m4a" type="audio/x-m4a" length="12345678"/>
    </item>
  </channel>
</rss>"""

DUPLICATE_GUID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>Description</description>
    <language>en</language>
    <lastBuildDate>Mon, 18 Dec 2025 10:45:30 +0000</lastBuildDate>
    <itunes:author>Author</itunes:author>
    <itunes:image href="https://example.com/artwork.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <item>
      <title>Episode 1</title>
      <description>Desc</description>
      <pubDate>Mon, 18 Dec 2025 10:00:00 +0000</pubDate>
      <guid>urn:uuid:same-guid</guid>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="12345678"/>
    </item>
    <item>
      <title>Episode 2</title>
      <description>Desc</description>
      <pubDate>Mon, 18 Dec 2025 11:00:00 +0000</pubDate>
      <guid>urn:uuid:same-guid</guid>
      <enclosure url="https://example.com/ep2.mp3" type="audio/mpeg" length="12345679"/>
    </item>
  </channel>
</rss>"""

MISSING_LANGUAGE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>Description</description>
    <lastBuildDate>Mon, 18 Dec 2025 10:45:30 +0000</lastBuildDate>
    <itunes:author>Author</itunes:author>
    <itunes:image href="https://example.com/artwork.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <item>
      <title>Episode 1</title>
      <description>Desc</description>
      <pubDate>Mon, 18 Dec 2025 10:00:00 +0000</pubDate>
      <guid>urn:uuid:ep-001</guid>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="12345678"/>
    </item>
  </channel>
</rss>"""

INVALID_DATE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>My Podcast</title>
    <link>https://example.com</link>
    <description>Description</description>
    <language>en</language>
    <lastBuildDate>not-a-date</lastBuildDate>
    <itunes:author>Author</itunes:author>
    <itunes:image href="https://example.com/artwork.jpg"/>
    <itunes:category text="Technology"/>
    <itunes:explicit>false</itunes:explicit>
    <item>
      <title>Episode 1</title>
      <description>Desc</description>
      <pubDate>not-a-date-either</pubDate>
      <guid>urn:uuid:ep-001</guid>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="12345678"/>
    </item>
  </channel>
</rss>"""


# ---------------------------------------------------------------------------
# Service unit tests (no DB, no network)
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
	return RSSValidationService()


def _channel(rss_xml: str) -> ET.Element:
	"""Parse RSS XML and return the <channel> element."""
	root = ET.fromstring(rss_xml)
	return root.find("channel")


@pytest.mark.asyncio
async def test_apple_valid_feed(service):
	"""Apple Podcasts validation passes for a well-formed feed."""
	channel = _channel(VALID_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_apple_podcasts(channel, now)

	assert result.valid is True
	assert result.errors == []


@pytest.mark.asyncio
async def test_apple_missing_required_fields(service):
	"""Apple Podcasts validation detects missing required channel fields."""
	channel = _channel(MISSING_REQUIRED_FIELDS_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_apple_podcasts(channel, now)

	assert result.valid is False
	error_fields = {e.field for e in result.errors}
	# Missing: link, description, language, itunes:author, itunes:image, itunes:category, itunes:explicit
	assert "link" in error_fields
	assert "description" in error_fields
	assert "language" in error_fields
	assert "itunes:author" in error_fields
	assert "itunes:category" in error_fields
	assert "itunes:explicit" in error_fields


@pytest.mark.asyncio
async def test_apple_invalid_audio_mime(service):
	"""Apple Podcasts allows audio/x-m4a — should pass."""
	channel = _channel(INVALID_AUDIO_MIME_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_apple_podcasts(channel, now)

	# audio/x-m4a is in APPLE_VALID_AUDIO_TYPES, so no enclosure type error
	enclosure_type_errors = [
		e for e in result.errors if e.field == "item/enclosure/@type"
	]
	assert enclosure_type_errors == []


@pytest.mark.asyncio
async def test_apple_duplicate_guids(service):
	"""Apple Podcasts validation detects duplicate GUIDs."""
	channel = _channel(DUPLICATE_GUID_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_apple_podcasts(channel, now)

	assert result.valid is False
	guid_errors = [e for e in result.errors if e.field == "item/guid"]
	assert len(guid_errors) >= 1


@pytest.mark.asyncio
async def test_spotify_invalid_audio_mime(service):
	"""Spotify validation rejects audio/x-m4a (strictly requires audio/mpeg)."""
	channel = _channel(INVALID_AUDIO_MIME_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_spotify(channel, now)

	assert result.valid is False
	enclosure_errors = [
		e for e in result.errors if e.field == "item/enclosure/@type"
	]
	assert len(enclosure_errors) == 1
	assert "audio/mpeg" in enclosure_errors[0].message


@pytest.mark.asyncio
async def test_spotify_valid_feed(service):
	"""Spotify validation passes for a feed with audio/mpeg."""
	channel = _channel(VALID_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_spotify(channel, now)

	assert result.valid is True
	assert result.errors == []


@pytest.mark.asyncio
async def test_spotify_duplicate_guids(service):
	"""Spotify validation detects duplicate GUIDs."""
	channel = _channel(DUPLICATE_GUID_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_spotify(channel, now)

	assert result.valid is False
	guid_errors = [e for e in result.errors if e.field == "item/guid"]
	assert len(guid_errors) >= 1


@pytest.mark.asyncio
async def test_google_missing_language(service):
	"""Google Podcasts validation detects missing language."""
	channel = _channel(MISSING_LANGUAGE_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_google_podcasts(channel, now)

	assert result.valid is False
	lang_errors = [e for e in result.errors if e.field == "language"]
	assert len(lang_errors) == 1


@pytest.mark.asyncio
async def test_google_missing_last_build_date(service):
	"""Google Podcasts validation detects missing lastBuildDate."""
	channel = _channel(MISSING_REQUIRED_FIELDS_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_google_podcasts(channel, now)

	assert result.valid is False
	date_errors = [e for e in result.errors if e.field == "lastBuildDate"]
	assert len(date_errors) == 1


@pytest.mark.asyncio
async def test_google_invalid_last_build_date(service):
	"""Google Podcasts validation detects invalid date format in lastBuildDate."""
	channel = _channel(INVALID_DATE_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_google_podcasts(channel, now)

	assert result.valid is False
	date_errors = [e for e in result.errors if e.field == "lastBuildDate"]
	assert len(date_errors) == 1


@pytest.mark.asyncio
async def test_apple_invalid_pub_date_in_episode(service):
	"""Apple Podcasts validation detects invalid pubDate in episode."""
	channel = _channel(INVALID_DATE_RSS)
	now = datetime.now(timezone.utc)

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service._validate_apple_podcasts(channel, now)

	assert result.valid is False
	date_errors = [e for e in result.errors if e.field == "item/pubDate"]
	assert len(date_errors) >= 1


def test_is_valid_rfc2822_valid():
	"""RFC 2822 validation accepts correct date strings."""
	assert RSSValidationService._is_valid_rfc2822("Mon, 18 Dec 2025 10:45:30 +0000") is True
	assert RSSValidationService._is_valid_rfc2822("Mon, 18 Dec 2025 10:45:30 GMT") is True


def test_is_valid_rfc2822_invalid():
	"""RFC 2822 validation rejects invalid date strings."""
	assert RSSValidationService._is_valid_rfc2822("not-a-date") is False
	assert RSSValidationService._is_valid_rfc2822("2025-12-18") is False
	assert RSSValidationService._is_valid_rfc2822("") is False


def test_is_valid_language_code_valid():
	"""Language code validation accepts BCP 47 codes."""
	assert RSSValidationService._is_valid_language_code("en") is True
	assert RSSValidationService._is_valid_language_code("en-US") is True
	assert RSSValidationService._is_valid_language_code("zh-Hans-CN") is True


def test_is_valid_language_code_invalid():
	"""Language code validation rejects invalid codes."""
	assert RSSValidationService._is_valid_language_code("") is False
	assert RSSValidationService._is_valid_language_code("english") is False
	assert RSSValidationService._is_valid_language_code("en_US") is False


@pytest.mark.asyncio
async def test_image_validation_inaccessible_url(service):
	"""Image validation reports warning when URL is not accessible."""
	import requests as _requests

	with patch("src.services.rss_validation_service.requests.get") as mock_get:
		mock_get.side_effect = _requests.exceptions.ConnectionError("Connection refused")
		errors = await service._validate_image("https://bad.example.com/image.jpg")

	assert len(errors) == 1
	assert errors[0].level == "warning"
	assert "fetch" in errors[0].message.lower()


@pytest.mark.asyncio
async def test_image_validation_wrong_content_type(service):
	"""Image validation reports error for non-image content type."""
	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.headers = {"content-type": "text/html"}
	mock_response.content = b"<html>not an image</html>"

	with patch("src.services.rss_validation_service.requests.get", return_value=mock_response):
		with patch("PIL.Image.open", side_effect=Exception("Not an image")):
			errors = await service._validate_image("https://example.com/not-image.html")

	content_errors = [e for e in errors if "JPG or PNG" in e.message]
	assert len(content_errors) >= 1


@pytest.mark.asyncio
async def test_image_validation_small_dimensions(service):
	"""Image validation reports error when image dimensions are too small."""
	from PIL import Image
	import io

	# Create a 100x100 JPEG image
	img = Image.new("RGB", (100, 100), color="red")
	img_bytes = io.BytesIO()
	img.save(img_bytes, format="JPEG")
	img_bytes.seek(0)
	image_content = img_bytes.read()

	mock_response = MagicMock()
	mock_response.status_code = 200
	mock_response.headers = {"content-type": "image/jpeg"}
	mock_response.content = image_content

	with patch("src.services.rss_validation_service.requests.get", return_value=mock_response):
		errors = await service._validate_image("https://example.com/small.jpg", min_dim=3000)

	dim_errors = [e for e in errors if "dimensions" in e.message.lower() or "pixels" in e.message.lower()]
	assert len(dim_errors) >= 1


@pytest.mark.asyncio
async def test_parse_invalid_xml(service):
	"""Invalid XML raises ET.ParseError."""
	with pytest.raises(ET.ParseError):
		service._parse_rss_xml("<not valid xml ><<<")


@pytest.mark.asyncio
async def test_parse_valid_xml(service):
	"""Valid XML parses without error."""
	root = service._parse_rss_xml(VALID_RSS)
	assert root.tag == "rss"


@pytest.mark.asyncio
async def test_full_validation_valid_feed(service):
	"""Full validate_rss_feed stores results and returns ValidationStatusUpdate."""
	mock_db = AsyncMock()

	# Create mock RSSFeed
	mock_rss_feed = MagicMock()
	mock_rss_feed.project_id = uuid4()
	mock_rss_feed.public_url = None
	mock_rss_feed.s3_key = None
	mock_rss_feed.validation_status = None

	mock_result = MagicMock()
	mock_result.scalar_one_or_none.return_value = mock_rss_feed
	mock_db.execute.return_value = mock_result

	with patch.object(service, "_validate_image", return_value=[]):
		result = await service.validate_rss_feed(
			db=mock_db,
			project_id=mock_rss_feed.project_id,
			rss_content=VALID_RSS,
		)

	assert isinstance(result, ValidationStatusUpdate)
	assert result.apple_podcasts.valid is True
	assert result.spotify.valid is True
	assert result.google_podcasts.valid is True
	assert result.is_valid_for_all is True
	# Results stored in model
	assert mock_rss_feed.validation_status is not None
	mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_full_validation_rss_not_found(service):
	"""validate_rss_feed raises ValueError when no RSSFeed record exists."""
	mock_db = AsyncMock()
	mock_result = MagicMock()
	mock_result.scalar_one_or_none.return_value = None
	mock_db.execute.return_value = mock_result

	with pytest.raises(ValueError, match="not found"):
		await service.validate_rss_feed(
			db=mock_db,
			project_id=uuid4(),
			rss_content=VALID_RSS,
		)


@pytest.mark.asyncio
async def test_get_validation_status_no_validation(service):
	"""get_validation_status raises ValueError when validation never run."""
	mock_db = AsyncMock()

	mock_rss_feed = MagicMock()
	mock_rss_feed.validation_status = None
	mock_result = MagicMock()
	mock_result.scalar_one_or_none.return_value = mock_rss_feed
	mock_db.execute.return_value = mock_result

	with pytest.raises(ValueError, match="validate first"):
		await service.get_validation_status(db=mock_db, project_id=uuid4())


@pytest.mark.asyncio
async def test_get_validation_status_returns_stored(service):
	"""get_validation_status returns previously stored validation results."""
	now = datetime.now(timezone.utc).isoformat()
	stored = {
		"last_validated_at": now,
		"apple_podcasts": {
			"directory": "apple_podcasts",
			"valid": True,
			"errors": [],
			"warnings": [],
			"checked_at": now,
		},
		"spotify": {
			"directory": "spotify",
			"valid": False,
			"errors": [
				{
					"field": "item/enclosure/@type",
					"level": "error",
					"message": "Invalid audio type",
					"details": None,
					"examples": None,
				}
			],
			"warnings": [],
			"checked_at": now,
		},
		"google_podcasts": {
			"directory": "google_podcasts",
			"valid": True,
			"errors": [],
			"warnings": [],
			"checked_at": now,
		},
		"is_valid_for_all": False,
	}

	mock_db = AsyncMock()
	mock_rss_feed = MagicMock()
	mock_rss_feed.validation_status = stored
	mock_result = MagicMock()
	mock_result.scalar_one_or_none.return_value = mock_rss_feed
	mock_db.execute.return_value = mock_result

	result = await service.get_validation_status(db=mock_db, project_id=uuid4())

	assert isinstance(result, ValidationStatusUpdate)
	assert result.is_valid_for_all is False
	assert result.spotify.valid is False
	assert len(result.spotify.errors) == 1


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def auth_headers(client):
	"""Register user and return auth headers."""
	response = await client.post("/auth/register", json={
		"email": f"rss_test_{uuid4()}@example.com",
		"password": "SecurePass123!",
		"full_name": "RSS Test User",
	})
	assert response.status_code == 201
	token = response.json()["access_token"]
	return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def user_tenant_id(client, auth_headers):
	"""Get the authenticated user's tenant_id."""
	response = await client.get("/auth/me", headers=auth_headers)
	assert response.status_code == 200
	return response.json()["tenant_id"]


@pytest.fixture
async def project_id(client, auth_headers):
	"""Create a project and return its ID."""
	response = await client.post("/projects", headers=auth_headers, json={
		"name": "RSS Test Project",
		"podcast_metadata": {
			"show_title": "Test Show",
			"author": "Test Author",
			"description": "Test podcast description",
		},
	})
	assert response.status_code == 201
	return response.json()["id"]


@pytest.mark.asyncio
async def test_validate_endpoint_no_feed(client, auth_headers, project_id):
	"""POST validate returns 404 when no RSS feed exists for the project."""
	response = await client.post(
		f"/projects/{project_id}/rss-feed/validate",
		headers=auth_headers,
		json={},
	)
	assert response.status_code == 404
	assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_validation_no_feed(client, auth_headers, project_id):
	"""GET validation returns 404 when no RSS feed exists for the project."""
	response = await client.get(
		f"/projects/{project_id}/rss-feed/validation",
		headers=auth_headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_validate_endpoint_requires_auth(client, project_id):
	"""POST validate returns 403 without authentication."""
	response = await client.post(
		f"/projects/{project_id}/rss-feed/validate",
		json={},
	)
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_validation_requires_auth(client, project_id):
	"""GET validation returns 403 without authentication."""
	response = await client.get(f"/projects/{project_id}/rss-feed/validation")
	assert response.status_code == 403


@pytest.mark.asyncio
async def test_validate_endpoint_with_rss_content(client, auth_headers, project_id, user_tenant_id, test_db):
	"""POST validate with rss_content validates feed and stores results."""
	from src.models.rss_feed import RSSFeed
	from uuid import UUID

	# Insert an RSSFeed record for this project
	rss_feed = RSSFeed(
		project_id=UUID(project_id),
		tenant_id=UUID(user_tenant_id),
		s3_key=None,
		public_url=None,
		validation_status=None,
	)
	test_db.add(rss_feed)
	await test_db.flush()

	with patch(
		"src.services.rss_validation_service.RSSValidationService._validate_image",
		return_value=[],
	):
		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=auth_headers,
			json={"rss_content": VALID_RSS},
		)

	assert response.status_code == 200
	data = response.json()
	assert "last_validated_at" in data
	assert "apple_podcasts" in data
	assert "spotify" in data
	assert "google_podcasts" in data
	assert "is_valid_for_all" in data
	assert data["apple_podcasts"]["directory"] == "apple_podcasts"
	assert data["apple_podcasts"]["valid"] is True


@pytest.mark.asyncio
async def test_validate_endpoint_with_invalid_xml(client, auth_headers, project_id, user_tenant_id, test_db):
	"""POST validate returns 422 when rss_content is invalid XML."""
	from src.models.rss_feed import RSSFeed
	from uuid import UUID

	rss_feed = RSSFeed(
		project_id=UUID(project_id),
		tenant_id=UUID(user_tenant_id),
		s3_key=None,
		public_url=None,
		validation_status=None,
	)
	test_db.add(rss_feed)
	await test_db.flush()

	response = await client.post(
		f"/projects/{project_id}/rss-feed/validate",
		headers=auth_headers,
		json={"rss_content": "<invalid xml ><< not parseable"},
	)
	assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_validation_after_validate(client, auth_headers, project_id, user_tenant_id, test_db):
	"""GET validation returns stored results after validation runs."""
	from src.models.rss_feed import RSSFeed
	from uuid import UUID

	rss_feed = RSSFeed(
		project_id=UUID(project_id),
		tenant_id=UUID(user_tenant_id),
		s3_key=None,
		public_url=None,
		validation_status=None,
	)
	test_db.add(rss_feed)
	await test_db.flush()

	# First validate
	with patch(
		"src.services.rss_validation_service.RSSValidationService._validate_image",
		return_value=[],
	):
		validate_resp = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=auth_headers,
			json={"rss_content": VALID_RSS},
		)
	assert validate_resp.status_code == 200

	# Then get stored results
	with patch(
		"src.services.rss_validation_service.RSSValidationService._validate_image",
		return_value=[],
	):
		get_resp = await client.get(
			f"/projects/{project_id}/rss-feed/validation",
			headers=auth_headers,
		)

	assert get_resp.status_code == 200
	data = get_resp.json()
	assert "apple_podcasts" in data
	assert "spotify" in data
	assert "google_podcasts" in data


@pytest.mark.asyncio
async def test_validate_endpoint_with_errors(client, auth_headers, project_id, user_tenant_id, test_db):
	"""POST validate returns validation errors for a bad feed."""
	from src.models.rss_feed import RSSFeed
	from uuid import UUID

	rss_feed = RSSFeed(
		project_id=UUID(project_id),
		tenant_id=UUID(user_tenant_id),
		s3_key=None,
		public_url=None,
		validation_status=None,
	)
	test_db.add(rss_feed)
	await test_db.flush()

	with patch(
		"src.services.rss_validation_service.RSSValidationService._validate_image",
		return_value=[],
	):
		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=auth_headers,
			json={"rss_content": MISSING_REQUIRED_FIELDS_RSS},
		)

	assert response.status_code == 200
	data = response.json()
	# Apple result should have errors (missing link, description, language, etc.)
	assert data["apple_podcasts"]["valid"] is False
	assert len(data["apple_podcasts"]["errors"]) > 0
	assert data["is_valid_for_all"] is False


@pytest.mark.asyncio
async def test_validate_nonexistent_project(client, auth_headers):
	"""POST validate returns 404 for non-existent project."""
	fake_id = str(uuid4())
	response = await client.post(
		f"/projects/{fake_id}/rss-feed/validate",
		headers=auth_headers,
		json={"rss_content": VALID_RSS},
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_validation_response_structure(client, auth_headers, project_id, user_tenant_id, test_db):
	"""Validate that the response includes all required fields."""
	from src.models.rss_feed import RSSFeed
	from uuid import UUID

	rss_feed = RSSFeed(
		project_id=UUID(project_id),
		tenant_id=UUID(user_tenant_id),
		s3_key=None,
		public_url=None,
		validation_status=None,
	)
	test_db.add(rss_feed)
	await test_db.flush()

	with patch(
		"src.services.rss_validation_service.RSSValidationService._validate_image",
		return_value=[],
	):
		response = await client.post(
			f"/projects/{project_id}/rss-feed/validate",
			headers=auth_headers,
			json={"rss_content": VALID_RSS},
		)

	assert response.status_code == 200
	data = response.json()

	# Check top-level fields
	assert "last_validated_at" in data
	assert "is_valid_for_all" in data

	# Check per-directory structure
	for directory in ("apple_podcasts", "spotify", "google_podcasts"):
		dir_data = data[directory]
		assert "directory" in dir_data
		assert "valid" in dir_data
		assert "errors" in dir_data
		assert "warnings" in dir_data
		assert "checked_at" in dir_data
