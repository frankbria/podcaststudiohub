"""Tests for the shipped nginx reverse-proxy config (issue #208).

The repo must serve the authenticated SaaS exclusively over HTTPS with modern
TLS and the standard set of security headers. These tests pin that contract so
a regression (e.g. re-commenting the SSL block) fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

CONF_PATH = Path(__file__).resolve().parents[1] / "nginx" / "podcastfy.conf"


def _block_matching(blocks: list[str], *needles: str) -> str:
	"""Return the first server block that contains every needle (case-insensitive)."""
	for block in blocks:
		if all(n.lower() in block.lower() for n in needles):
			return block
	raise AssertionError(
		"No server block contained all of: " + ", ".join(needles)
	)


# ── Existence ──────────────────────────────────────────────────────────────


def test_config_file_exists():
	assert CONF_PATH.is_file(), f"Expected nginx config at {CONF_PATH}"


# ── AC1: HTTP → HTTPS redirect + 443 server block ───────────────────────────


def test_http_listens_on_80_and_redirects_to_https(server_blocks: list[str]):
	block = _block_matching(server_blocks, "listen 80")
	assert "return 301 https://" in block.lower(), (
		"port-80 server block must 301-redirect to HTTPS, not serve content"
	)


def test_http_block_does_not_proxy_to_backend(server_blocks: list[str]):
	"""The cleartext port must never reach the app — only redirect."""
	block = _block_matching(server_blocks, "listen 80")
	assert "proxy_pass" not in block.lower(), (
		"port-80 server block must not proxy_pass (would leak auth over HTTP)"
	)


def test_https_listens_on_443_ssl(server_blocks: list[str]):
	block = _block_matching(server_blocks, "listen 443 ssl")
	assert "ssl_certificate" in block.lower()
	assert "ssl_certificate_key" in block.lower()


# ── AC2: TLS protocols (1.2 / 1.3 only) ────────────────────────────────────


def test_tls_protocols_modern_only(nginx_conf_raw: str):
	assert "ssl_protocols" in nginx_conf_raw
	m = re.search(r"ssl_protocols\s+([^;]+);", nginx_conf_raw)
	assert m, "ssl_protocols directive missing"
	tokens = m.group(1).split()
	assert "TLSv1.2" in tokens and "TLSv1.3" in tokens
	# No legacy protocols enabled (token-exact so TLSv1.2 is not matched by TLSv1).
	for forbidden in ("SSLv2", "SSLv3", "TLSv1", "TLSv1.1"):
		assert forbidden not in tokens, f"legacy protocol {forbidden!r} must not be enabled"


# ── AC2: Security headers ──────────────────────────────────────────────────


def test_security_headers_present(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	required = [
		"Strict-Transport-Security",
		"Content-Security-Policy",
		"X-Frame-Options",
		"X-Content-Type-Options",
		"Referrer-Policy",
	]
	for header in required:
		assert header.lower() in https_block.lower(), (
			f"missing security header in 443 block: {header}"
		)


def test_hsts_directive_is_strict(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	m = re.search(r"Strict-Transport-Security[^;]*max-age=(\d+)", https_block, re.I)
	assert m, "HSTS header with max-age not found"
	assert int(m.group(1)) >= 15552000, "HSTS max-age must be >= 6 months"
	assert "includesubdomains" in https_block.lower()
	assert "preload" in https_block.lower()


def test_frame_options_denies_frame(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	m = re.search(r"X-Frame-Options\s+([^;]+)", https_block, re.I)
	assert m, "X-Frame-Options header missing"
	assert "deny" in m.group(1).lower() or "sameorigin" in m.group(1).lower()


# ── AC1: Let's Encrypt cert paths + renewal webroot ─────────────────────────


def test_uses_letsencrypt_cert_paths(nginx_conf_raw: str):
	assert "/etc/letsencrypt/live/" in nginx_conf_raw, (
		"cert paths should reference Let's Encrypt (/etc/letsencrypt/live/)"
	)


def test_acme_challenge_webroot_for_renewal(server_blocks: list[str]):
	# Renewal needs a webroot-served challenge path reachable over HTTP.
	text = " ".join(server_blocks).lower()
	assert "acme-challenge" in text, (
		".well-known/acme-challenge location required for cert renewal"
	)


# ── Real nginx syntax validation (Docker) ──────────────────────────────────


def test_config_loads_in_real_nginx(nginx_syntax_ok):
	ok, output = nginx_syntax_ok
	assert ok, f"nginx -t failed against the shipped config:\n{output}"
