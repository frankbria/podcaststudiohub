"""Tests for deployment hardening (issue #209).

The API must never be exposed publicly: it binds the loopback interface only
(nginx already proxies to 127.0.0.1:8001), the deploy port must match the nginx
upstream, services run as a dedicated non-root account, and a host firewall
blocks direct external access. These tests pin that contract so a regression
(re-binding 0.0.0.0, a port drift, or a root deploy) fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-dev.yml"
CONFIG = REPO_ROOT / "apps" / "api" / "src" / "config.py"
NGINX_CONF = REPO_ROOT / "deployment" / "nginx" / "podcastfy.conf"
HARDEN_SCRIPT = REPO_ROOT / "deployment" / "scripts" / "harden-host.sh"


def _nginx_upstream_port() -> str:
	m = re.search(r"upstream\s+podcastfy_api\s*\{[^}]*?127\.0\.0\.1:(\d+)", NGINX_CONF.read_text())
	assert m, "could not find the FastAPI upstream port in the nginx config"
	return m.group(1)


# ── AC2: API binds loopback, not 0.0.0.0 ───────────────────────────────────


def test_workflow_uvicorn_binds_loopback():
	text = WORKFLOW.read_text()
	uvicorn_lines = [ln for ln in text.splitlines() if "uvicorn src.main:app" in ln]
	assert uvicorn_lines, "deploy workflow no longer starts uvicorn — update this test"
	for ln in uvicorn_lines:
		assert "--host 127.0.0.1" in ln, f"uvicorn must bind loopback: {ln.strip()}"
		assert "0.0.0.0" not in ln, f"uvicorn must not bind 0.0.0.0: {ln.strip()}"


def test_config_default_host_is_loopback():
	m = re.search(r'API_HOST:\s*str\s*=\s*"([^"]+)"', CONFIG.read_text())
	assert m, "API_HOST default not found in config.py"
	assert m.group(1) == "127.0.0.1", "API_HOST must default to loopback, not 0.0.0.0"


# ── AC2: deploy port matches the nginx upstream ────────────────────────────


def test_workflow_deploy_port_matches_nginx_upstream():
	port = _nginx_upstream_port()
	text = WORKFLOW.read_text()
	# The uvicorn launch must fall back to the nginx upstream port, not 8000.
	assert f"--port ${{API_PORT:-{port}}}" in text, (
		f"deploy port fallback must match nginx upstream ({port})"
	)
	assert "${API_PORT:-8000}" not in text, "stale 8000 port fallback drifts from nginx upstream"


# ── AC3: DEBUG / reload off in prod ────────────────────────────────────────


def test_config_debug_defaults_off():
	m = re.search(r"DEBUG:\s*bool\s*=\s*(\w+)", CONFIG.read_text())
	assert m and m.group(1) == "False", "DEBUG must default to False (reload is gated on DEBUG)"


# ── AC1 + AC3: host-hardening provisioning script ──────────────────────────


def test_harden_script_exists_and_executable():
	assert HARDEN_SCRIPT.is_file(), f"expected host-hardening script at {HARDEN_SCRIPT}"
	assert HARDEN_SCRIPT.stat().st_mode & 0o111, "harden-host.sh must be executable"


def test_harden_script_creates_nonroot_user_and_firewall():
	text = HARDEN_SCRIPT.read_text()
	assert "useradd" in text, "script must create a dedicated service account"
	assert "ufw" in text, "script must configure the host firewall"
	# Firewall must permit SSH + HTTP(S) and default-deny everything else inbound.
	assert "ufw default deny incoming" in text, "firewall must default-deny inbound"
	# SSH must be allowed by port (22), not the openssh-server "OpenSSH" app
	# profile, so a missing profile can't abort the script post-default-deny.
	for allowed in ("22/tcp", "80/tcp", "443/tcp"):
		assert allowed in text, f"firewall must allow {allowed}"


def test_harden_script_installs_pm2_startup_for_service_user():
	"""Migrating PM2 off root must leave the service account's processes
	resurrecting on reboot — otherwise services stay down after a restart."""
	text = HARDEN_SCRIPT.read_text()
	assert "pm2 startup" in text, "must install a boot-time PM2 unit for the service account"
	m = re.search(r"pm2 startup[^\n]*-u\s+\"?\$\{?SERVICE_USER", text)
	assert m, "pm2 startup must target the dedicated service account, not root"


# ── AC1: docs no longer assume a root deploy ───────────────────────────────


def test_readme_documents_nonroot_service_account():
	readme = (REPO_ROOT / "deployment" / "README.md").read_text()
	assert "harden-host.sh" in readme, "README must reference the host-hardening script"
	assert "non-root" in readme.lower() or "service account" in readme.lower(), (
		"README must document the dedicated non-root service account"
	)
