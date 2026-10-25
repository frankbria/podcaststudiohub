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

	remote_npm = [ln for ln in text.splitlines() if re.search(r"ssh .*\bnpm (ci|install|run)\b", ln)]
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


STUB_NVM = 'nvm() {{ echo "nvm $*" >> "{log}"; }}\n'


def _run_prelude(tmp_path: Path, node_version: str, nvm_stub: str | None = STUB_NVM):
	"""Run the deploy's USE_NODE the way the workflow does: assigned by the runner's
	shell, interpolated into a double-quoted ssh command, parsed by the remote shell.
	`nvm` is a stub; `node` reports `node_version`."""
	home = tmp_path / "home"
	frontend = tmp_path / "frontend"
	bindir = tmp_path / "bin"
	for d in (home, frontend, bindir):
		d.mkdir()
	(frontend / ".nvmrc").write_text(NVMRC.read_text())
	if nvm_stub:
		(home / ".nvm").mkdir()
		(home / ".nvm" / "nvm.sh").write_text(nvm_stub.format(log=tmp_path / "nvm.log"))
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
	r = _run_prelude(tmp_path, f"v{_major()}.0.0", nvm_stub=None)
	assert r.returncode == 1
	assert "nvm is not installed" in r.stdout
	assert "NPM_RAN" not in r.stdout


def test_a_runtime_bump_alone_redeploys():
	triggers = DEPLOY.read_text().split("workflow_dispatch:")[0]
	assert "- '.nvmrc'" in triggers


def test_prelude_falls_back_to_an_installed_node_when_install_fails(tmp_path):
	offline = 'nvm() {{ echo "nvm $*" >> "{log}"; [ "$1" != install ]; }}\n'
	r = _run_prelude(tmp_path, f"v{_major()}.3.1", nvm_stub=offline)
	assert r.returncode == 0, r.stderr
	assert "NPM_RAN" in r.stdout
	assert (tmp_path / "nvm.log").read_text().split("\n")[:2] == ["nvm install", "nvm use"]


# --- #564: prune superseded patches from the deploy user's nvm ---

PRUNE_STUB = (
	'nvm() {{ case "$1" in current) echo "{current}" ;; '
	'uninstall) echo "$2" >> "{log}"; [ "$2" != "{current}" ] && rm -rf "$NVM_DIR/versions/node/$2" ;; esac; }}\n'
)


def _run_prune(tmp_path: Path, installed: list[str], current: str) -> list[str]:
	"""Run the deploy's PRUNE_NODE as the remote shell receives it (expanded once
	by the runner inside the restart heredoc). Returns the versions left installed."""
	nvm_dir = tmp_path / ".nvm"
	frontend = tmp_path / "frontend"
	frontend.mkdir()
	(frontend / ".nvmrc").write_text(NVMRC.read_text())
	for v in installed:
		(nvm_dir / "versions" / "node" / v).mkdir(parents=True)
	(nvm_dir / "nvm.sh").write_text(PRUNE_STUB.format(current=current, log=tmp_path / "uninstall.log"))

	assign = re.search(r"^\s*(PRUNE_NODE='[^']+')$", DEPLOY.read_text(), re.M).group(1)
	remote = subprocess.run(
		["bash", "-c", f"{assign}\ncat << EOF\n$PRUNE_NODE\nEOF"], capture_output=True, text=True, check=True
	).stdout
	script = f'export NVM_DIR="{nvm_dir}"; . "$NVM_DIR/nvm.sh"; cd {frontend} || exit 1\n{remote}'
	r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
	assert r.returncode == 0, r.stderr
	return sorted(p.name for p in (nvm_dir / "versions" / "node").iterdir())


def test_prune_keeps_the_running_node_and_one_prior(tmp_path):
	m = _major()
	left = _run_prune(tmp_path, [f"v{m}.9.0", f"v{m}.10.0", f"v{m}.11.0", f"v{m}.12.0"], current=f"v{m}.12.0")
	# Version order, not string order: 11 is the prior, 9 and 10 go.
	assert left == [f"v{m}.11.0", f"v{m}.12.0"]


def test_prune_never_removes_the_running_node_even_when_it_is_not_the_newest(tmp_path):
	m = _major()
	left = _run_prune(tmp_path, [f"v{m}.1.0", f"v{m}.2.0", f"v{m}.3.0"], current=f"v{m}.1.0")
	assert left == [f"v{m}.1.0", f"v{m}.3.0"]
	assert f"v{m}.1.0" not in (tmp_path / "uninstall.log").read_text()


def test_prune_leaves_other_majors_alone(tmp_path):
	m = _major()
	left = _run_prune(tmp_path, ["v20.19.0", "v22.1.0", f"v{m}0.1.0", f"v{m}.1.0", f"v{m}.2.0"], current=f"v{m}.2.0")
	assert left == sorted(["v20.19.0", "v22.1.0", f"v{m}0.1.0", f"v{m}.1.0", f"v{m}.2.0"])
	assert not (tmp_path / "uninstall.log").exists()


def test_prune_runs_after_the_frontend_restart_in_the_same_remote_shell():
	text = DEPLOY.read_text()
	start = text.index("pm2 start npm")
	prune = text.index("$PRUNE_NODE", start)
	assert prune < text.index("EOF", start), "prune must run inside the restart heredoc, after pm2 start"
