#!/usr/bin/env python3
"""Write the npm workspace root the dev VPS installs from.

The VPS keeps the frontend at $SERVER_PATH/frontend, not apps/web, so the repo's
root package-lock.json cannot be used there as-is, and a bare `npm install` in
frontend/ re-resolves every range to the newest release and drops the root
`overrides`. This rewrites the root package.json and lockfile for that layout
(workspace "apps/web" -> "frontend") without re-resolving anything, so
`npm ci` in $SERVER_PATH installs exactly what CI tested.

Usage: vps-npm-root.py <repo-root> <out-dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WORKSPACE = "apps/web"
VPS_DIR = "frontend"


def _rename(key: str) -> str:
	if key == WORKSPACE or key.startswith(WORKSPACE + "/"):
		return VPS_DIR + key[len(WORKSPACE):]
	return key


def build(root_pkg: dict, lock: dict) -> tuple[dict, dict]:
	"""Return (package.json, package-lock.json) for the VPS layout."""
	packages = lock["packages"]
	others = [
		k for k, v in packages.items()
		if v.get("link") and v.get("resolved") != WORKSPACE
	]
	if WORKSPACE not in packages or others:
		raise ValueError(f"expected exactly one workspace ({WORKSPACE}); other links: {others}")

	pkg = dict(root_pkg, workspaces=[VPS_DIR])
	out = {}
	for key, entry in packages.items():
		entry = dict(entry)
		if key == "":
			entry["workspaces"] = [VPS_DIR]
		if entry.get("link"):
			entry["resolved"] = VPS_DIR
		out[_rename(key)] = entry
	return pkg, dict(lock, packages=out)


def main(repo_root: str, out_dir: str) -> None:
	root, out = Path(repo_root), Path(out_dir)
	pkg, lock = build(
		json.loads((root / "package.json").read_text()),
		json.loads((root / "package-lock.json").read_text()),
	)
	out.mkdir(parents=True, exist_ok=True)
	(out / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")
	(out / "package-lock.json").write_text(json.dumps(lock, indent=2) + "\n")


if __name__ == "__main__":
	if len(sys.argv) != 3:
		sys.exit(__doc__)
	main(sys.argv[1], sys.argv[2])
