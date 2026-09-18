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
import subprocess
from pathlib import Path

import pytest

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
	assert '. "$NVM_DIR/nvm.sh"' in guard.group(1)

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


def _run_prelude(tmp_path: Path, node_version: str | None, with_nvm: bool = True):
	"""Run the deploy's USE_NODE the way the workflow does: assigned by the runner's
	shell, interpolated into a double-quoted ssh command, parsed by the remote shell.
	`nvm` is a stub; `node` reports `node_version`."""
	home = tmp_path / "home"
	frontend = tmp_path / "frontend"
	bindir = tmp_path / "bin"
	for d in (home, frontend, bindir):
		d.mkdir()
	(frontend / ".nvmrc").write_text(NVMRC.read_text())
	if with_nvm:
		(home / ".nvm").mkdir()
		(home / ".nvm" / "nvm.sh").write_text(f'nvm() {{ echo "nvm $*" >> "{tmp_path}/nvm.log"; }}\n')
	node = bindir / "node"
	node.write_text(f"#!/bin/sh\necho {node_version}\n")
	node.chmod(0o755)

	assign = re.search(r"^\s*(USE_NODE='[^']+')$", DEPLOY.read_text(), re.M).group(1)
	remote = f'{assign}; printf %s "cd {frontend} || exit 1; $USE_NODE; echo NPM_RAN"'
	command = subprocess.run(["bash", "-c", remote], capture_output=True, text=True, check=True).stdout
	env = {"HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin"}
	return subprocess.run(["bash", "-c", command], capture_output=True, text=True, env=env)


def test_prelude_runs_npm_on_the_nvmrc_major_and_logs_it(tmp_path):
	r = _run_prelude(tmp_path, f"v{_major()}.3.1")
	assert r.returncode == 0, r.stderr
	assert f"node -v: v{_major()}.3.1" in r.stdout
	assert "NPM_RAN" in r.stdout
	assert (tmp_path / "nvm.log").read_text().strip() == "nvm install"


@pytest.mark.parametrize("wrong", ["v20.19.0", f"v{_major()}0.0.0", "v2.0.0"])
def test_prelude_fails_before_npm_on_a_mismatch(tmp_path, wrong):
	r = _run_prelude(tmp_path, wrong)
	assert r.returncode == 1
	assert f"wrong node: {wrong}" in r.stdout
	assert "NPM_RAN" not in r.stdout


def test_prelude_fails_before_npm_without_nvm(tmp_path):
	r = _run_prelude(tmp_path, f"v{_major()}.0.0", with_nvm=False)
	assert r.returncode == 1
	assert "nvm is not installed" in r.stdout
	assert "NPM_RAN" not in r.stdout


def test_a_runtime_bump_alone_redeploys():
	triggers = DEPLOY.read_text().split("workflow_dispatch:")[0]
	assert "- '.nvmrc'" in triggers
