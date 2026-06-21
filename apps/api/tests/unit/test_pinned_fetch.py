"""
Unit tests for the IP-pinned fetch helpers (src.utils.pinned_fetch, issue #234).

These prove that outbound fetches connect to the IP the SSRF guard validated
rather than re-resolving the hostname at connect time (DNS-rebinding TOCTOU).
No network access is required: the urllib3 socket chokepoint is stubbed.
"""

import os

# Set required env vars before any src import
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.adapters import HTTPAdapter

from src.utils.pinned_fetch import _ip_netloc, pin_httpx, pinned_session


# ---------------------------------------------------------------------------
# _ip_netloc
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
	"ip,port,expected",
	[
		("203.0.113.5", None, "203.0.113.5"),
		("203.0.113.5", 8443, "203.0.113.5:8443"),
		("2001:db8::1", None, "[2001:db8::1]"),
		("2001:db8::1", 443, "[2001:db8::1]:443"),
	],
)
def test_ip_netloc(ip, port, expected):
	assert _ip_netloc(ip, port) == expected


# ---------------------------------------------------------------------------
# pinned_session (requests)
# ---------------------------------------------------------------------------

def test_pinned_session_https_rewrites_host_and_preserves_sni():
	session = pinned_session("https://example.com/path?q=1", "203.0.113.5")
	adapter = session.get_adapter("https://example.com/path?q=1")

	# TLS still verified/SNI'd against the hostname, not the IP.
	pool_kw = adapter.poolmanager.connection_pool_kw
	assert pool_kw["server_hostname"] == "example.com"
	assert pool_kw["assert_hostname"] == "example.com"

	# send() rewrites the URL to the pinned IP and keeps the Host header.
	prepared = requests.Request("GET", "https://example.com/path?q=1").prepare()
	with patch.object(HTTPAdapter, "send", return_value=MagicMock()) as mock_super:
		adapter.send(prepared)
	sent = mock_super.call_args.args[0]
	assert sent.url == "https://203.0.113.5/path?q=1"
	assert sent.headers["Host"] == "example.com"


def test_pinned_session_http_has_no_tls_pool_kwargs():
	session = pinned_session("http://example.com/", "203.0.113.5")
	adapter = session.get_adapter("http://example.com/")
	pool_kw = adapter.poolmanager.connection_pool_kw
	assert "server_hostname" not in pool_kw
	assert "assert_hostname" not in pool_kw


def test_pinned_session_preserves_explicit_port():
	session = pinned_session("https://example.com:443/x", "203.0.113.5")
	adapter = session.get_adapter("https://example.com:443/x")
	prepared = requests.Request("GET", "https://example.com:443/x").prepare()
	with patch.object(HTTPAdapter, "send", return_value=MagicMock()) as mock_super:
		adapter.send(prepared)
	sent = mock_super.call_args.args[0]
	assert sent.url == "https://203.0.113.5:443/x"
	assert sent.headers["Host"] == "example.com:443"


def test_pinned_session_connects_to_pinned_ip_not_hostname():
	"""
	DNS-rebinding proof: even though the URL names a hostname, the socket layer
	is asked to connect to the validated IP literal. urllib3's create_connection
	chokepoint records the target host.
	"""
	captured = []

	def fake_create_connection(address, *args, **kwargs):
		# Record the connect target (host, port), then fail like an unreachable
		# socket so urllib3 wraps it into a requests ConnectionError.
		captured.append(address)
		raise OSError("pinned-stop")

	session = pinned_session("https://malicious.example/path", "203.0.113.5")
	with patch(
		"urllib3.util.connection.create_connection",
		side_effect=fake_create_connection,
	):
		with pytest.raises(requests.exceptions.ConnectionError):
			session.get(
				"https://malicious.example/path",
				timeout=1,
				allow_redirects=False,
			)

	# Connected to the validated IP literal on the default HTTPS port — never
	# the (rebindable) hostname.
	assert captured == [("203.0.113.5", 443)]


def test_pinned_session_brackets_ipv6_pinned_ip():
	"""An IPv6 pinned IP is bracketed in the rewritten URL; Host stays the name."""
	ip = "2001:db8::1"
	session = pinned_session("https://example.com/path", ip)
	adapter = session.get_adapter("https://example.com/path")
	prepared = requests.Request("GET", "https://example.com/path").prepare()
	with patch.object(HTTPAdapter, "send", return_value=MagicMock()) as mock_super:
		adapter.send(prepared)
	sent = mock_super.call_args.args[0]
	assert sent.url == f"https://[{ip}]/path"
	assert sent.headers["Host"] == "example.com"


# ---------------------------------------------------------------------------
# pin_httpx
# ---------------------------------------------------------------------------

def test_pinned_session_rejects_hostless_url():
	with pytest.raises(ValueError):
		pinned_session("https:///nohost", "203.0.113.5")


def test_pin_httpx_rejects_hostless_url():
	with pytest.raises(ValueError):
		pin_httpx("https:///nohost", "203.0.113.5")


def test_pin_httpx_builds_ip_url_with_sni_and_host():
	url, headers, extensions = pin_httpx("https://example.com/a/b?q=1", "203.0.113.5")
	assert url == "https://203.0.113.5/a/b?q=1"
	assert headers["Host"] == "example.com"
	assert extensions["sni_hostname"] == "example.com"


def test_pin_httpx_preserves_port_and_brackets_ipv6():
	url, headers, extensions = pin_httpx(
		"https://example.com:443/x", "2001:db8::1"
	)
	assert url == "https://[2001:db8::1]:443/x"
	assert headers["Host"] == "example.com:443"
	assert extensions["sni_hostname"] == "example.com"
