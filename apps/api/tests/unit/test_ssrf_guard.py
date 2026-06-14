"""
Unit tests for the SSRF guard (src.utils.ssrf).

Implements the protections required by issue #206: resolve the host and reject
loopback / link-local / private / reserved IP targets (including the cloud
metadata endpoint 169.254.169.254) and non-standard ports — at validation and
dispatch time.

IP-literal hosts resolve offline via getaddrinfo, so these tests are
deterministic and require no network access.
"""

import os

# Set required env vars before any src import
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import socket
from unittest.mock import patch

import pytest

from src.utils.ssrf import (
	SSRFValidationError,
	is_public_ip,
	validate_public_url,
)


# ---------------------------------------------------------------------------
# is_public_ip
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
	"ip",
	[
		"169.254.169.254",   # AWS/GCP metadata (link-local)
		"127.0.0.1",         # loopback
		"0.0.0.0",           # unspecified
		"10.0.0.1",          # RFC1918
		"172.16.0.1",        # RFC1918
		"192.168.1.1",       # RFC1918
		"100.64.0.1",        # CGNAT (RFC6598)
		"::1",               # IPv6 loopback
		"fd00::1",           # IPv6 ULA (private)
		"fe80::1",           # IPv6 link-local
		"::ffff:169.254.169.254",  # IPv4-mapped metadata
		"::ffff:127.0.0.1",        # IPv4-mapped loopback
	],
)
def test_internal_ips_are_not_public(ip):
	assert is_public_ip(ip) is False


@pytest.mark.parametrize(
	"ip",
	[
		"104.20.23.154",     # public IPv4
		"8.8.8.8",           # public IPv4
		"2606:4700:10::6814:179a",  # public IPv6
	],
)
def test_public_ips_are_public(ip):
	assert is_public_ip(ip) is True


# ---------------------------------------------------------------------------
# validate_public_url — internal targets rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
	"url",
	[
		"http://169.254.169.254/latest/meta-data/",
		"https://169.254.169.254/",
		"http://127.0.0.1/",
		"https://127.0.0.1/admin",
		"http://10.0.0.1/",
		"http://172.16.5.4/",
		"http://192.168.1.1/",
		"http://[::1]/",
		"http://[::ffff:169.254.169.254]/",
		"http://0.0.0.0/",
	],
)
def test_validate_public_url_rejects_internal(url):
	with pytest.raises(SSRFValidationError):
		validate_public_url(url)


def test_validate_public_url_rejects_localhost_hostname():
	# localhost resolves to 127.0.0.1 via /etc/hosts (offline)
	with pytest.raises(SSRFValidationError):
		validate_public_url("http://localhost/")


def test_validate_public_url_rejects_decimal_ip_form():
	# 2130706433 == 127.0.0.1; getaddrinfo normalizes numeric forms
	with pytest.raises(SSRFValidationError):
		validate_public_url("http://2130706433/")


# ---------------------------------------------------------------------------
# validate_public_url — scheme & port rules
# ---------------------------------------------------------------------------

def test_validate_public_url_rejects_non_http_scheme():
	with pytest.raises(SSRFValidationError):
		validate_public_url("ftp://example.com/")


def test_validate_public_url_rejects_non_standard_port():
	with pytest.raises(SSRFValidationError):
		validate_public_url("http://93.184.216.34:8080/")


def test_validate_public_url_https_only_rejects_http():
	with pytest.raises(SSRFValidationError):
		validate_public_url(
			"http://93.184.216.34/", allowed_schemes=("https",), allowed_ports={443}
		)


def test_validate_public_url_https_only_rejects_8443():
	with pytest.raises(SSRFValidationError):
		validate_public_url(
			"https://93.184.216.34:8443/",
			allowed_schemes=("https",),
			allowed_ports={443},
		)


def test_validate_public_url_rejects_empty():
	with pytest.raises(SSRFValidationError):
		validate_public_url("")


# ---------------------------------------------------------------------------
# validate_public_url — public targets allowed
# ---------------------------------------------------------------------------

def test_validate_public_url_allows_public_ip_literal():
	ips = validate_public_url("https://93.184.216.34/")
	assert "93.184.216.34" in ips


def test_validate_public_url_allows_public_with_default_https_port():
	# No explicit port -> default 443 allowed for https-only callers
	ips = validate_public_url(
		"https://93.184.216.34/path",
		allowed_schemes=("https",),
		allowed_ports={443},
	)
	assert ips == ["93.184.216.34"]


def test_validate_public_url_allows_unresolvable_host():
	# NXDOMAIN: no IP to attack. Must NOT raise — dispatch-time re-check
	# covers DNS rebinding. Returns empty list.
	with patch("src.utils.ssrf.socket.getaddrinfo", side_effect=socket.gaierror):
		assert validate_public_url("https://hooks.example.com/notify") == []


def test_validate_public_url_blocks_unresolvable_when_strict():
	# Dispatch paths set block_on_resolution_failure=True: NXDOMAIN must raise.
	with patch("src.utils.ssrf.socket.getaddrinfo", side_effect=socket.gaierror):
		with pytest.raises(SSRFValidationError):
			validate_public_url(
				"https://hooks.example.com/notify",
				block_on_resolution_failure=True,
			)


def test_validate_public_url_rejects_when_any_resolved_ip_is_private():
	# DNS rebinding: one public + one private A record -> reject.
	def fake_getaddrinfo(host, port, *a, **k):
		return [
			(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
			(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
		]

	with patch("src.utils.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo):
		with pytest.raises(SSRFValidationError):
			validate_public_url("https://rebind.example.com/")
