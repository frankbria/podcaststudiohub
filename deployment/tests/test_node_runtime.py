"""Tests for the Node runtime pin (issue #522).

Node 20 went EOL on 2026-04-30. The runtime major now lives in one place — the
root `.nvmrc` — and everything else must follow it: every CI setup-node step
reads the file, the manifests match its major, and the dev deploy selects that
runtime on the VPS through the deploy user's nvm (never the box's system node,
which other tenants share) and fails when it gets anything else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NVMRC = REPO_ROOT / ".nvmrc"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy-dev.yml"


def _major() -> str:
	return NVMRC.read_text().strip()


def test_nvmrc_pins_node_24():
	assert _major() == "24"


def test_every_setup_node_step_reads_nvmrc():
	setup_steps = 0
	for wf in WORKFLOWS.glob("*.yml"):
		text = wf.read_text()
		assert not re.search(r"^\s*node-version:", text, re.M), f"{wf.name} hardcodes node-version"
		setup_steps += text.count("actions/setup-node@")
		assert text.count("actions/setup-node@") == text.count("node-version-file: '.nvmrc'"), wf.name
	assert setup_steps >= 8


def test_manifests_match_runtime_major():
	root = json.loads((REPO_ROOT / "package.json").read_text())
	web = json.loads((REPO_ROOT / "apps" / "web" / "package.json").read_text())
	assert root["engines"]["node"] == f">={_major()}"
	assert web["devDependencies"]["@types/node"] == f"^{_major()}"


def test_deploy_ships_nvmrc_to_the_frontend_dir():
	assert re.search(r"rsync[^\n]*\\\n(\s+\S+ \\\n)*\s+\.nvmrc \\", DEPLOY.read_text())


def test_deploy_selects_node_before_every_remote_npm_call():
	text = DEPLOY.read_text()
	guard = re.search(r"USE_NODE='([^']+)'", text)
	assert guard, "deploy-dev.yml must define the USE_NODE prelude"
	prelude = guard.group(1)
	assert '. "$NVM_DIR/nvm.sh"' in prelude
	assert "nvm install" in prelude
	assert '"v$(cat .nvmrc)".*)' in prelude and "exit 1" in prelude
	assert 'node -v' in prelude

	remote_npm = [ln for ln in text.splitlines() if re.search(r"ssh .*\bnpm (install|run)\b", ln)]
	assert len(remote_npm) == 2, remote_npm
	for ln in remote_npm:
		assert "$USE_NODE" in ln, ln

	pm2_start = text.index("pm2 start npm")
	assert text.rfind("$USE_NODE", 0, pm2_start) > text.rfind("ssh $SSH_USER@$SSH_HOST", 0, pm2_start)
	assert '--interpreter "\\$(command -v node)"' in text[pm2_start : pm2_start + 300]


def test_deploy_never_changes_the_system_node():
	text = DEPLOY.read_text()
	assert "/usr/local/bin/node" not in text
	assert "nvm alias default" not in text
