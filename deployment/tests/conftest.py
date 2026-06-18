"""Shared fixtures for the deployment nginx config tests.

These tests intentionally have NO dependency on the application runtime: they
read the shipped nginx config file and (optionally) validate it loads inside a
real ``nginx:stable`` container. That keeps them runnable from a bare
``python -m pytest deployment/tests/`` invocation in CI.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

CONF_PATH = Path(__file__).resolve().parents[1] / "nginx" / "podcastfy.conf"


def _strip_comments(text: str) -> str:
	"""Remove ``#`` comments so directive checks do not match commented-out lines."""
	cleaned = []
	for line in text.splitlines():
		hash_idx = line.find("#")
		if hash_idx != -1:
			line = line[:hash_idx]
		cleaned.append(line)
	return "\n".join(cleaned)


def _extract_server_blocks(text: str) -> list[str]:
	"""Return the body of every top-level ``server { ... }`` block (brace balanced)."""
	blocks: list[str] = []
	for m in re.finditer(r"\bserver\s*\{", text):
		start = m.end()
		depth = 1
		i = start
		while i < len(text) and depth > 0:
			if text[i] == "{":
				depth += 1
			elif text[i] == "}":
				depth -= 1
			i += 1
		if depth == 0:
			blocks.append(text[start : i - 1])
	return blocks


@pytest.fixture(scope="module")
def nginx_conf_raw() -> str:
	"""Raw config text (comments stripped)."""
	return _strip_comments(CONF_PATH.read_text())


@pytest.fixture(scope="module")
def server_blocks(nginx_conf_raw: str) -> list[str]:
	return _extract_server_blocks(nginx_conf_raw)


def _docker_available() -> bool:
	if not shutil.which("docker"):
		return False
	try:
		subprocess.run(
			["docker", "info"],
			check=True,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			timeout=20,
		)
		return True
	except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
		return False


@pytest.fixture(scope="module")
def nginx_syntax_ok() -> tuple[bool, str]:
	"""Run the shipped config through a real ``nginx -t`` inside ``nginx:stable``.

	Self-signed certs are generated at the Let's Encrypt path the config points
	at, and the directories the config writes logs / webroot into are created so
	the test exercises the *real* loadability of the file — not just its text.
	Skipped when Docker is unavailable.
	"""
	if not _docker_available():
		pytest.skip("Docker is not available; cannot run real nginx -t")

	nginx_dir = str(CONF_PATH.parent)
	cmd = (
		"set -e; "
		"mkdir -p /etc/letsencrypt/live/dev.podcaststudiohub.me "
		"/opt/podcaststudiohub/logs /var/www/html; "
		"openssl req -x509 -nodes -newkey rsa:2048 "
		"-keyout /etc/letsencrypt/live/dev.podcaststudiohub.me/privkey.pem "
		"-out /etc/letsencrypt/live/dev.podcaststudiohub.me/fullchain.pem "
		"-days 1 -subj '/CN=localhost' >/dev/null 2>&1; "
		"nginx -t"
	)
	proc = subprocess.run(
		[
			"docker",
			"run",
			"--rm",
			"-v",
			f"{nginx_dir}:/etc/nginx/conf.d:ro",
			"nginx:stable",
			"bash",
			"-c",
			cmd,
		],
		capture_output=True,
		text=True,
		timeout=60,
	)
	combined = (proc.stdout or "") + (proc.stderr or "")
	return (proc.returncode == 0, combined)
