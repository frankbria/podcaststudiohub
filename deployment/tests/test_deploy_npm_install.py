"""Tests for how the dev deploy installs frontend dependencies.

The VPS used to run a bare `npm install` in frontend/: it ignored the lockfile
(staging ran next 16.4.3 while CI had tested 16.4.1) and the root `overrides`.
It now runs `npm ci` from the repo lockfile, rewritten by
deployment/scripts/vps-npm-root.py for the VPS layout. Deploys are serialized,
because five overlapping runs crashed one mid-install.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy-dev.yml"
SCRIPT = REPO_ROOT / "deployment" / "scripts" / "vps-npm-root.py"


def _script():
	spec = importlib.util.spec_from_file_location("vps_npm_root", SCRIPT)
	assert spec and spec.loader
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def _built():
	root = json.loads((REPO_ROOT / "package.json").read_text())
	lock = json.loads((REPO_ROOT / "package-lock.json").read_text())
	return root, lock, *_script().build(root, lock)


def test_workspace_is_renamed_to_frontend_and_nothing_else_changes():
	root, lock, pkg, out = _built()
	packages, renamed = lock["packages"], out["packages"]

	assert pkg["workspaces"] == ["frontend"]
	assert renamed[""]["workspaces"] == ["frontend"]
	assert pkg["overrides"] == root["overrides"]
	assert not any(k == "apps/web" or k.startswith("apps/web/") for k in renamed)
	assert renamed["frontend"] == packages["apps/web"]
	assert renamed["node_modules/web"] == {"resolved": "frontend", "link": True}
	assert len(renamed) == len(packages)
	for key, entry in packages.items():
		if key.startswith("node_modules/") and not entry.get("link"):
			assert renamed[key] == entry, key  # versions/integrity are untouched


def test_nested_workspace_deps_keep_their_pins():
	_, lock, _, out = _built()
	nested = {k: v for k, v in lock["packages"].items() if k.startswith("apps/web/node_modules/")}
	assert nested, "lockfile has no workspace-nested deps; this test no longer guards anything"
	for key, entry in nested.items():
		assert out["packages"]["frontend" + key[len("apps/web"):]] == entry


def test_a_second_workspace_is_refused():
	lock = {"packages": {
		"": {}, "apps/web": {}, "node_modules/web": {"resolved": "apps/web", "link": True},
		"node_modules/other": {"resolved": "packages/other", "link": True},
	}}
	with pytest.raises(ValueError, match="exactly one workspace"):
		_script().build({}, lock)


def test_deploy_installs_with_npm_ci_from_the_shipped_lockfile():
	text = DEPLOY.read_text()
	assert not re.search(r"ssh .*\bnpm install\b", text), "the VPS must not re-resolve with npm install"
	ci = [ln for ln in text.splitlines() if re.search(r"ssh .*\bnpm ci\b", ln)]
	assert len(ci) == 1, ci
	assert "rm -rf package-lock.json node_modules" in ci[0]
	assert re.search(r'vps-npm-root/package-lock\.json" \\\n\s+\$SSH_USER@\$SSH_HOST:\$SERVER_PATH/', text)


def test_lockfile_is_checked_before_the_box_is_touched():
	text = DEPLOY.read_text()
	prepare = text.index("- name: Prepare VPS npm root")
	assert "npm ci --dry-run" in text[prepare : text.index("- name:", prepare + 1)]
	assert prepare < text.index("- name: Connect to Tailscale")


def test_deploys_are_serialized_not_cancelled():
	text = DEPLOY.read_text()
	block = re.search(r"^concurrency:\n((?:  .*\n)+)", text, re.M)
	assert block, "deploy-dev.yml needs a workflow-level concurrency group"
	assert re.search(r"^  group: \S+", block.group(1), re.M)
	assert "cancel-in-progress: false" in block.group(1)
