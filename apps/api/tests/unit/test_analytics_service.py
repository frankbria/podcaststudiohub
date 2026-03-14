"""
Unit tests for analytics service helper functions.

Tests IP hashing and device/app detection logic without requiring a database.
"""

import hashlib

from src.models.analytics_event import AnalyticsEvent
from src.services.analytics_service import _detect_device_type, _detect_app_name


# ---------------------------------------------------------------------------
# IP hashing
# ---------------------------------------------------------------------------

def test_hash_ip_deterministic():
	"""Same IP should always produce the same hash."""
	ip = "192.168.1.1"
	assert AnalyticsEvent.hash_ip(ip) == AnalyticsEvent.hash_ip(ip)


def test_hash_ip_uses_sha256():
	"""IP hash should match SHA-256 of the IP string."""
	ip = "10.0.0.1"
	expected = hashlib.sha256(ip.encode()).hexdigest()
	assert AnalyticsEvent.hash_ip(ip) == expected


def test_hash_ip_not_reversible():
	"""Hash should not contain the original IP."""
	ip = "8.8.8.8"
	assert ip not in AnalyticsEvent.hash_ip(ip)


def test_hash_ip_different_ips_differ():
	"""Different IPs should produce different hashes."""
	assert AnalyticsEvent.hash_ip("1.1.1.1") != AnalyticsEvent.hash_ip("8.8.8.8")


# ---------------------------------------------------------------------------
# Device type detection
# ---------------------------------------------------------------------------

def test_detect_device_mobile_android():
	ua = "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36"
	assert _detect_device_type(ua) == "mobile"


def test_detect_device_mobile_iphone():
	ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
	assert _detect_device_type(ua) == "mobile"


def test_detect_device_tablet_ipad():
	ua = "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)"
	assert _detect_device_type(ua) == "tablet"


def test_detect_device_desktop_windows():
	ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
	assert _detect_device_type(ua) == "desktop"


def test_detect_device_desktop_mac():
	ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
	assert _detect_device_type(ua) == "desktop"


def test_detect_device_unknown_no_ua():
	assert _detect_device_type(None) == "unknown"


def test_detect_device_unknown_empty():
	assert _detect_device_type("") == "unknown"


# ---------------------------------------------------------------------------
# App name detection
# ---------------------------------------------------------------------------

def test_detect_app_spotify():
	ua = "Spotify/8.7.72 iOS/15.6 (iPhone12,1)"
	assert _detect_app_name(ua) == "spotify"


def test_detect_app_overcast():
	ua = "Overcast/2021.9.20 (+http://overcast.fm/; iOS podcast app)"
	assert _detect_app_name(ua) == "overcast"


def test_detect_app_apple_podcasts():
	ua = "AppleCoreMedia/1.0.0.19A346 (Apple Podcasts)"
	assert _detect_app_name(ua) == "apple_podcasts"


def test_detect_app_none_no_ua():
	assert _detect_app_name(None) is None


def test_detect_app_other_unknown_app():
	ua = "SomeRandomApp/1.0"
	assert _detect_app_name(ua) == "other"
