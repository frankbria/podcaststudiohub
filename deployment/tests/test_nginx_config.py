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
	# Must redirect to a canonical host, NOT $host (Host-header open-redirect).
	assert "$host" not in block, (
		"redirect must use a canonical host, not the attacker-controllable $host"
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
	matches = re.findall(r"ssl_protocols\s+([^;]+);", nginx_conf_raw, flags=re.I)
	assert matches, "ssl_protocols directive missing"
	# Check EVERY ssl_protocols directive — a later block must not re-enable legacy TLS.
	for raw in matches:
		tokens = raw.split()
		assert "TLSv1.2" in tokens and "TLSv1.3" in tokens
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


def test_csp_allows_s3_audio(server_blocks: list[str]):
	"""Episode audio streams / downloads from S3 (apps/web episode page +
	DownloadButton). CSP must not block it — both media-src (<audio>) and
	connect-src (fetch download) must allow an S3 origin."""
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	m = re.search(r"Content-Security-Policy\s+\"([^\"]+)\"", https_block, re.I)
	assert m, "Content-Security-Policy header missing"
	csp = m.group(1)

	def directive(src: str) -> str:
		match = re.search(rf"{src}\s+([^;]+)", csp)
		return match.group(1) if match else ""

	# An S3 host must be permitted for both media playback and fetch downloads.
	assert any(".s3." in tok for tok in directive("media-src").split()), (
		"media-src must allow the S3 audio host (episode playback)"
	)
	assert any(".s3." in tok for tok in directive("connect-src").split()), (
		"connect-src must allow the S3 audio host (download fetch)"
	)


# ── AC1: Let's Encrypt cert paths + renewal webroot ─────────────────────────


def test_uses_letsencrypt_cert_paths(nginx_conf_raw: str):
	assert "/etc/letsencrypt/live/" in nginx_conf_raw, (
		"cert paths should reference Let's Encrypt (/etc/letsencrypt/live/)"
	)


def test_acme_challenge_webroot_for_renewal(server_blocks: list[str]):
	# Renewal needs a webroot-served challenge path reachable over HTTP (port 80),
	# not just HTTPS — otherwise HTTP-01 renewal breaks.
	http_block = _block_matching(server_blocks, "listen 80")
	http_lower = http_block.lower()
	assert "/.well-known/acme-challenge/" in http_lower, (
		".well-known/acme-challenge location required on port 80 for HTTP-01 renewal"
	)
	assert "root /var/www/html" in http_lower, (
		"ACME challenge on port 80 must use the expected webroot"
	)


# ── /api/* routing contract: Next.js vs FastAPI ownership ───────────────────
#
# The Next.js app owns /api/auth/* (NextAuth csrf/callback/session/error) and
# /api/proxy/* (server-side JWT proxy + SSE). FastAPI owns the rest of /api/,
# plus two carve-outs the app calls directly at ${NEXT_PUBLIC_API_URL}/auth/…:
# /api/auth/login (NextAuth authorize()) and /api/auth/register (signup page,
# E2E global-setup). Routing all of /api/ to FastAPI breaks browser login with
# a redirect to /api/auth/error that itself 404s in FastAPI (#302).


def _location_block(server_block: str, path: str) -> str:
	"""Return the body of ``location <path> { ... }`` inside a server block."""
	m = re.search(rf"location\s+{re.escape(path)}\s*\{{", server_block)
	assert m, f"location {path} missing from the 443 server block"
	start = m.end()
	depth = 1
	i = start
	while i < len(server_block) and depth > 0:
		if server_block[i] == "{":
			depth += 1
		elif server_block[i] == "}":
			depth -= 1
		i += 1
	return server_block[start : i - 1]


def test_frontend_location_is_pure_reverse_proxy(server_blocks: list[str]):
	"""root/try_files inside the proxy location short-circuits proxy_pass and
	500s on an internal redirection cycle for every non-file URI (e.g. /login)."""
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	loc = _location_block(https_block, "/")
	assert "proxy_pass" in loc, "location / must reverse-proxy to Next.js"
	assert "try_files" not in loc, "try_files must not appear in the Next.js proxy location"
	assert re.search(r"\broot\b", loc) is None, "root must not appear in the Next.js proxy location"


def test_nextauth_routes_go_to_frontend(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	loc = _location_block(https_block, "/api/auth/")
	assert "127.0.0.1:3010" in loc, "/api/auth/ (NextAuth) must proxy to the Next.js app"
	assert "podcastfy_api" not in loc


def test_jwt_proxy_routes_go_to_frontend_with_sse(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	loc = _location_block(https_block, "/api/proxy/")
	assert "127.0.0.1:3010" in loc, "/api/proxy/ (JWT proxy + SSE) must proxy to the Next.js app"
	assert "proxy_buffering off" in loc, "SSE through /api/proxy/ requires proxy_buffering off"


def test_fastapi_auth_carveouts_reach_backend(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	for path in ("/api/auth/login", "/api/auth/register"):
		loc = _location_block(https_block, path)
		assert "podcastfy_api" in loc, f"{path} must reach the FastAPI backend"
		assert "rewrite ^/api/(.*) /$1 break" in loc, f"{path} must strip the /api prefix"


def test_api_catchall_still_reaches_backend(server_blocks: list[str]):
	https_block = _block_matching(server_blocks, "listen 443 ssl")
	loc = _location_block(https_block, "/api/")
	assert "podcastfy_api" in loc


# ── Real nginx syntax validation (Docker) ──────────────────────────────────


def test_config_loads_in_real_nginx(nginx_syntax_ok):
	ok, output = nginx_syntax_ok
	assert ok, f"nginx -t failed against the shipped config:\n{output}"
