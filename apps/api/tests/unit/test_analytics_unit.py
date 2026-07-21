"""
Unit tests for analytics utilities and service helpers.
These tests do not require a database connection.
"""

import pytest


# ---------------------------------------------------------------------------
# IP hashing
# ---------------------------------------------------------------------------


class TestIPHashing:
	def test_hash_ip_returns_sha256_hex(self):
		from src.models.analytics_event import hash_ip
		result = hash_ip("192.168.1.1")
		assert len(result) == 64
		assert all(c in "0123456789abcdef" for c in result)

	def test_hash_ip_is_deterministic(self):
		from src.models.analytics_event import hash_ip
		assert hash_ip("10.0.0.1") == hash_ip("10.0.0.1")

	def test_hash_ip_different_ips_produce_different_hashes(self):
		from src.models.analytics_event import hash_ip
		assert hash_ip("1.2.3.4") != hash_ip("5.6.7.8")

	def test_hash_ip_not_reversible(self):
		from src.models.analytics_event import hash_ip
		# A SHA-256 hash should not contain the original IP
		result = hash_ip("192.168.100.200")
		assert "192.168.100.200" not in result


# ---------------------------------------------------------------------------
# Device type detection
# ---------------------------------------------------------------------------


class TestDeviceTypeDetection:
	def test_detects_mobile_android(self):
		from src.models.analytics_event import detect_device_type
		ua = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"
		assert detect_device_type(ua) == "mobile"

	def test_detects_mobile_iphone(self):
		from src.models.analytics_event import detect_device_type
		ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)"
		assert detect_device_type(ua) == "mobile"

	def test_detects_tablet_ipad(self):
		from src.models.analytics_event import detect_device_type
		ua = "Mozilla/5.0 (iPad; CPU OS 16_0)"
		assert detect_device_type(ua) == "tablet"

	def test_detects_desktop_windows(self):
		from src.models.analytics_event import detect_device_type
		ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
		assert detect_device_type(ua) == "desktop"

	def test_detects_desktop_mac(self):
		from src.models.analytics_event import detect_device_type
		ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)"
		assert detect_device_type(ua) == "desktop"

	def test_unknown_for_empty_ua(self):
		from src.models.analytics_event import detect_device_type
		assert detect_device_type("") == "unknown"

	def test_unknown_for_unrecognized_ua(self):
		from src.models.analytics_event import detect_device_type
		assert detect_device_type("MyCustomBot/1.0") == "unknown"


# ---------------------------------------------------------------------------
# App name detection
# ---------------------------------------------------------------------------


class TestAppNameDetection:
	def test_detects_apple_podcasts(self):
		from src.models.analytics_event import detect_app_name
		ua = "AppleCoreMedia/1.0.0.20C65 (iPhone; U; CPU OS 16_2)"
		assert detect_app_name(ua) == "apple_podcasts"

	def test_detects_spotify(self):
		from src.models.analytics_event import detect_app_name
		ua = "Spotify/8.7 iOS/16.1 (iPhone12,1)"
		assert detect_app_name(ua) == "spotify"

	def test_detects_overcast(self):
		from src.models.analytics_event import detect_app_name
		ua = "Overcast/1.0 (+http://overcast.fm/)"
		assert detect_app_name(ua) == "overcast"

	def test_detects_pocket_casts(self):
		from src.models.analytics_event import detect_app_name
		ua = "PocketCasts/7.0 (iOS)"
		assert detect_app_name(ua) == "pocket_casts"

	def test_unknown_for_empty_ua(self):
		from src.models.analytics_event import detect_app_name
		assert detect_app_name("") == "unknown"

	def test_other_for_browser(self):
		from src.models.analytics_event import detect_app_name
		ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
		assert detect_app_name(ua) == "other"


# ---------------------------------------------------------------------------
# Country normalization (issue #325)
# ---------------------------------------------------------------------------


class TestCountryNormalization:
	def test_uppercases_and_trims(self):
		from src.models.analytics_event import normalize_country
		assert normalize_country("  gb ") == "GB"
		assert normalize_country("us") == "US"

	def test_none_and_empty_return_none(self):
		from src.models.analytics_event import normalize_country
		assert normalize_country(None) is None
		assert normalize_country("") is None
		assert normalize_country("   ") is None

	def test_cloudflare_sentinels_return_none(self):
		from src.models.analytics_event import normalize_country
		# XX = unknown, T1 = Tor exit — must not pollute top_countries
		assert normalize_country("XX") is None
		assert normalize_country("xx") is None
		assert normalize_country("T1") is None
		assert normalize_country(" t1 ") is None

	def test_non_alpha2_shapes_rejected(self):
		from src.models.analytics_event import normalize_country
		# Header is client-settable (X-Country spoofable) — free-form junk and
		# wrong-length codes must not create bogus top_countries buckets.
		for junk in ("FAKE", "ZZZZ", "U", "USA", "U1", "1S", "U.S"):
			assert normalize_country(junk) is None, junk


# ---------------------------------------------------------------------------
# build_event_payload threads a normalized country (issue #325)
# ---------------------------------------------------------------------------


class TestBuildEventPayloadCountry:
	def _payload(self, **over):
		from uuid import uuid4
		from src.services.analytics_service import build_event_payload
		return build_event_payload(tenant_id=uuid4(), event_type="download", **over)

	def test_normalizes_country_into_payload(self):
		assert self._payload(country=" gb ")["country"] == "GB"

	def test_absent_country_defaults_to_none(self):
		assert self._payload()["country"] is None

	def test_sentinel_country_stored_as_none(self):
		assert self._payload(country="XX")["country"] is None


# ---------------------------------------------------------------------------
# Event type validation
# ---------------------------------------------------------------------------


class TestEventTypeValidation:
	def test_valid_event_types(self):
		from src.models.analytics_event import VALID_EVENT_TYPES
		assert "download" in VALID_EVENT_TYPES
		assert "play" in VALID_EVENT_TYPES
		assert "share" in VALID_EVENT_TYPES
		assert "stream" in VALID_EVENT_TYPES

	def test_schema_rejects_invalid_event_type(self):
		from src.schemas.analytics import TrackEventRequest
		with pytest.raises(Exception):
			TrackEventRequest(event_type="invalid_type")

	def test_schema_accepts_valid_event_type(self):
		from src.schemas.analytics import TrackEventRequest
		req = TrackEventRequest(event_type="download")
		assert req.event_type == "download"
