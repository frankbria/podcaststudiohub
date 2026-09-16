"""Tests for the nginx config drift gate (issue #491).

The nginx site config is operator-installed (root-run, from a root-owned clone),
so the deploy workflow never touches it — and the dev box ran a pre-#307 copy
for two months, stacking a stale ``'unsafe-inline'`` CSP on top of the
middleware's nonce policy. Committing the config is only worth anything if a
deploy asserts the live copy still matches it. These tests pin that gate: the
check script exists, diffs the right file with the same substitutions
provision-ssl.sh applies, the workflow runs it after the health check, and —
run against an ``ssh`` shim — it passes on an in-sync box and fails loudly on
a drifted one.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deployment" / "scripts" / "check-nginx-drift.sh"
CONF = REPO_ROOT / "deployment" / "nginx" / "podcastfy.conf"
PROVISION = REPO_ROOT / "deployment" / "scripts" / "provision-ssl.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-dev.yml"
README = REPO_ROOT / "deployment" / "README.md"
LIVE_PATH = "/etc/nginx/sites-available/podcastfy"


# ── Script contract ────────────────────────────────────────────────────────


def test_script_exists_and_is_executable():
	assert SCRIPT.is_file(), f"expected drift check script at {SCRIPT}"
	assert SCRIPT.stat().st_mode & stat.S_IXUSR, f"{SCRIPT.name} must be executable"


def test_script_fails_fast():
	assert "set -euo pipefail" in SCRIPT.read_text()


def test_script_diffs_the_installed_site_file():
	text = SCRIPT.read_text()
	assert LIVE_PATH in text, "must read the file provision-ssl.sh installs"
	assert "diff" in text, "must diff live vs committed"


def test_script_mirrors_provisioning_substitutions():
	"""provision-ssl.sh rewrites DOMAIN / API_PORT / FRONTEND_PORT into the
	installed copy; the drift check must render the committed file the same
	way or every non-default environment reports permanent drift."""
	text = SCRIPT.read_text()
	provision = PROVISION.read_text()
	for pattern in (
		r"s/dev\.podcaststudiohub\.me/",
		r"s/127\.0\.0\.1:8005/",
		r"s/127\.0\.0\.1:3010/",
	):
		assert pattern in provision, f"provision-ssl.sh no longer applies {pattern} — update this test"
		assert pattern in text, f"drift check must apply the same substitution: {pattern}"


# ── Workflow wiring ────────────────────────────────────────────────────────


def test_workflow_runs_drift_check_after_health_check():
	text = WORKFLOW.read_text()
	health = text.find("- name: Health Check")
	drift = text.find("check-nginx-drift.sh")
	assert health != -1, "deploy workflow lost its Health Check step — update this test"
	assert drift != -1, "deploy workflow must run deployment/scripts/check-nginx-drift.sh"
	assert drift > health, "drift check must run after the deploy + health check, not block it"


def test_workflow_passes_ports_to_drift_check():
	text = WORKFLOW.read_text()
	step = text[text.find("check-nginx-drift.sh") - 800 : text.find("check-nginx-drift.sh")]
	assert "API_PORT: ${{ vars.API_PORT }}" in step
	assert "FRONTEND_PORT: ${{ vars.FRONTEND_PORT }}" in step


def test_readme_documents_the_gate():
	text = README.read_text()
	assert "check-nginx-drift.sh" in text
	assert "/root/podcaststudiohub" in text


# ── Functional: run the script against an ssh shim ─────────────────────────


@pytest.fixture
def ssh_shim(tmp_path: Path):
	"""Put a fake ``ssh`` on PATH that prints ``$LIVE_CONF`` instead of dialing out."""
	bin_dir = tmp_path / "bin"
	bin_dir.mkdir()
	shim = bin_dir / "ssh"
	shim.write_text('#!/usr/bin/env bash\ncat "$LIVE_CONF"\n')
	shim.chmod(0o755)

	def run(live_text: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
		live = tmp_path / "live.conf"
		live.write_text(live_text)
		env = {
			**os.environ,
			"PATH": f"{bin_dir}:{os.environ['PATH']}",
			"LIVE_CONF": str(live),
			"SSH_HOST": "box.invalid",
			"SSH_USER": "deploy",
			"API_PORT": "8005",
			"FRONTEND_PORT": "3010",
			**extra_env,
		}
		return subprocess.run(
			["bash", str(SCRIPT)],
			env=env,
			capture_output=True,
			text=True,
			timeout=30,
			check=False,
		)

	return run


def test_in_sync_box_passes(ssh_shim):
	proc = ssh_shim(CONF.read_text())
	assert proc.returncode == 0, proc.stdout + proc.stderr


def test_drifted_box_fails_loudly_with_diff(ssh_shim):
	stale = CONF.read_text().replace(
		"add_header X-Frame-Options",
		"add_header Content-Security-Policy \"script-src 'self' 'unsafe-inline'\" always;\n"
		"\tadd_header X-Frame-Options",
		1,
	)
	proc = ssh_shim(stale)
	assert proc.returncode != 0, "a drifted live config must fail the check"
	out = proc.stdout + proc.stderr
	assert "'unsafe-inline'" in out, "the offending live line must appear in the diff"
	assert LIVE_PATH in out, "the failure must name the live file to re-sync"


def test_port_override_renders_like_provisioning(ssh_shim):
	"""A non-dev environment installs the conf with its own ports; the check
	must compare against that rendering, not the committed dev defaults."""
	rendered = CONF.read_text().replace("127.0.0.1:8005", "127.0.0.1:8100").replace(
		"127.0.0.1:3010", "127.0.0.1:3100"
	)
	proc = ssh_shim(rendered, API_PORT="8100", FRONTEND_PORT="3100")
	assert proc.returncode == 0, proc.stdout + proc.stderr
	# ...and the unrendered dev defaults now count as drift for that environment.
	proc = ssh_shim(CONF.read_text(), API_PORT="8100", FRONTEND_PORT="3100")
	assert proc.returncode != 0
