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
HARDEN_SCRIPT = REPO_ROOT / "deployment" / "scripts" / "harden-host.sh"


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


def test_workflow_requires_explicit_numeric_api_port():
	# The deploy host is multi-tenant, so the API port is per-environment (the
	# environment's API_PORT variable, which must match that environment's nginx
	# upstream) rather than a single repo-wide constant. The workflow must NOT
	# hardcode an equality check against one port, and must reject an unset or
	# non-numeric API_PORT so a missing/typo'd value fails fast.
	text = WORKFLOW.read_text()
	# No silent default and no hardcoded single-port equality (the old 8000/8001 drift guard).
	assert "${API_PORT:-" not in text, "API_PORT must be explicit, not a silent default"
	assert '!= "8001"' not in text and '!= "8000"' not in text, (
		"deploy must not hardcode a single API port; it is per-environment"
	)
	# Unset / non-numeric API_PORT must hard-fail before the service is torn down.
	assert "*[!0-9]*" in text and "exit 1" in text, (
		"deploy must reject an unset or non-numeric API_PORT"
	)


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


def test_harden_script_installs_aws_cli():
	"""backup-db.sh pushes to S3 via the AWS CLI and runs as the service account,
	so provisioning must install `aws` — otherwise the pre-migration dump (which
	gates every deploy) dies with 'aws: command not found' once S3 is configured.
	The distro only ships v1, so it must come from AWS's official installer."""
	text = HARDEN_SCRIPT.read_text()
	assert "awscli-exe-linux" in text, (
		"harden-host.sh must install AWS CLI v2 from AWS's official bundle "
		"(backup-db.sh needs `aws` on the service account's PATH)"
	)
	# Idempotent AND version-correct: the guard must check for aws-cli/2 on the
	# guard line itself, not just any `aws` — a distro v1 would otherwise satisfy a
	# presence-only check and the v2 requirement would silently go unmet (codex,
	# PR #405). Match the actual `aws --version … aws-cli/2` guard, not comment
	# prose that merely mentions the version.
	assert re.search(r"aws --version[^\n]*aws-cli/2", text), (
		"AWS CLI install must gate on `aws --version … aws-cli/2`, so v1-only boxes "
		"still get upgraded (a bare `command -v aws` would skip them)"
	)
	# curl + unzip are used by the install and may be absent on a minimal image;
	# provisioning must ensure them or `set -e` aborts mid-run (codex, PR #405).
	assert "curl unzip" in text or ("install -y" in text and "curl" in text and "unzip" in text), (
		"harden-host.sh must ensure curl and unzip before the AWS CLI download"
	)


# ── AC1: docs no longer assume a root deploy ───────────────────────────────


def test_readme_documents_nonroot_service_account():
	readme = (REPO_ROOT / "deployment" / "README.md").read_text()
	assert "harden-host.sh" in readme, "README must reference the host-hardening script"
	assert "non-root" in readme.lower() or "service account" in readme.lower(), (
		"README must document the dedicated non-root service account"
	)
