"""Tests for the observability baseline's log/readiness plumbing (issue #320).

Pins three deployment-side contracts:
1. The deploy gates on the API's *readiness* endpoint (/ready — DB+Redis
   reachable), not merely liveness (/health), so a deploy that leaves the API
   up but its dependencies unreachable fails loudly instead of going green.
   nginx must expose /ready for that gate to be reachable at all.
2. nginx's logs land on a custom path (/opt/podcaststudiohub/logs/*.log) that
   the distro's stock /etc/logrotate.d/nginx does NOT cover (it globs
   /var/log/nginx/*.log) — a repo-owned drop-in rotates them, and the deploy
   installs + validates it.
3. PM2's per-process logs (~/.pm2/logs) are rotated by the pm2-logrotate
   module, configured idempotently by the deploy.

Static reads only, like test_dr_durability.py — no live server/nginx/PM2.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-dev.yml"
NGINX_CONF = REPO_ROOT / "deployment" / "nginx" / "podcastfy.conf"
LOGROTATE_CONF = REPO_ROOT / "deployment" / "logrotate" / "podcaststudiohub-nginx"
README = REPO_ROOT / "deployment" / "README.md"

LOGROTATE_INSTALL_PATH = "/etc/logrotate.d/podcaststudiohub-nginx"


# ── AC1: the deploy gates on /ready, not /health ───────────────────────────


def test_deploy_gates_api_on_ready_endpoint():
	text = DEPLOY_WORKFLOW.read_text()
	assert re.search(r'wait_for "API" "\$API_URL/ready" "200"', text), (
		"deploy must gate the API on /ready (DB+Redis reachable), not just liveness"
	)


def test_deploy_does_not_gate_api_on_liveness_health():
	# /health returns 200 whenever the process is merely up — gating on it lets
	# a deploy go green with an unreachable DB or Redis.
	text = DEPLOY_WORKFLOW.read_text()
	assert not re.search(r'wait_for "API" "\$API_URL/health"', text), (
		"the API gate must not fall back to the liveness endpoint"
	)


def test_deploy_still_gates_frontend():
	text = DEPLOY_WORKFLOW.read_text()
	assert re.search(r'wait_for "Frontend" "\$FRONTEND_URL" "200"', text), (
		"the frontend gate must be preserved"
	)


def test_deploy_keeps_polling_readiness_gate():
	# A cold uvicorn start is slow; /ready is slower still (it dials DB+Redis).
	# The retry helper must stay — a one-shot curl would race the upstream.
	text = DEPLOY_WORKFLOW.read_text()
	assert "attempts=30" in text, "readiness gate must keep the 30-attempt poll"
	assert "sleep 5" in text, "readiness gate must keep the 5s backoff"


def test_deploy_explains_ready_versus_health():
	# The distinction is subtle enough to regress silently; it must be written down.
	text = DEPLOY_WORKFLOW.read_text()
	gate = text.find('wait_for "API"')
	assert gate != -1
	window = text[gate - 1200 : gate]
	assert "/ready" in window and "/health" in window, (
		"deploy must comment why the gate is /ready (readiness) not /health (liveness)"
	)


# ── AC1: nginx exposes /ready ──────────────────────────────────────────────


def test_nginx_exposes_ready_location():
	text = NGINX_CONF.read_text()
	assert re.search(r"location /ready\b", text), (
		"nginx must expose /ready or the deploy gate can never reach it"
	)


def test_nginx_ready_proxies_to_api_upstream():
	text = NGINX_CONF.read_text()
	match = re.search(r"location /ready\b[^{]*\{(.*?)\n\t\}", text, re.S)
	assert match, "expected a brace-delimited location /ready block"
	body = match.group(1)
	assert "proxy_pass http://podcastfy_api/ready;" in body, (
		"/ready must proxy to the FastAPI upstream's /ready"
	)


def test_nginx_ready_does_not_pollute_access_log():
	# The deploy polls /ready up to 30x per run, and uptime checks hit it
	# continuously — mirroring /health's access_log off keeps it out of the logs
	# this same issue teaches to rotate.
	text = NGINX_CONF.read_text()
	match = re.search(r"location /ready\b[^{]*\{(.*?)\n\t\}", text, re.S)
	assert match
	assert "access_log off;" in match.group(1), "/ready must set access_log off"


def test_nginx_keeps_health_location():
	# /ready is additive: /health stays as the liveness probe.
	text = NGINX_CONF.read_text()
	assert re.search(r"location /health\b", text), "the /health location must be preserved"


# ── AC2: nginx logrotate drop-in ───────────────────────────────────────────


def test_logrotate_conf_exists():
	assert LOGROTATE_CONF.is_file(), f"expected logrotate drop-in at {LOGROTATE_CONF}"


def test_logrotate_targets_the_custom_nginx_log_path():
	# The whole point: podcastfy.conf logs to /opt/podcaststudiohub/logs/, which
	# the stock nginx drop-in (/var/log/nginx/*.log) never touches.
	text = LOGROTATE_CONF.read_text()
	assert "/opt/podcaststudiohub/logs/*.log" in text, (
		"drop-in must rotate the custom log path nginx actually writes to"
	)


def test_logrotate_conf_covers_the_paths_nginx_writes():
	# Guard the pairing: if podcastfy.conf's access_log/error_log move, the glob
	# must move with them or the logs go unrotated again.
	nginx = NGINX_CONF.read_text()
	logs = re.findall(r"^\s*(?:access|error)_log\s+(\S+\.log);", nginx, re.M)
	assert logs, "expected nginx to configure file-backed access/error logs"
	for path in logs:
		assert path.startswith("/opt/podcaststudiohub/logs/"), (
			f"nginx log {path} is outside the rotated glob — it would grow forever"
		)


def test_logrotate_rotates_daily_with_retention():
	text = LOGROTATE_CONF.read_text()
	assert re.search(r"^\s*daily\s*$", text, re.M), "must rotate daily"
	assert re.search(r"^\s*rotate\s+14\s*$", text, re.M), "must retain 14 rotations"


def test_logrotate_compresses_with_delaycompress():
	text = LOGROTATE_CONF.read_text()
	assert re.search(r"^\s*compress\s*$", text, re.M), "must compress rotated logs"
	# delaycompress: nginx keeps writing to the renamed file until it reopens on
	# USR1, so compressing on the same pass would truncate in-flight lines.
	assert re.search(r"^\s*delaycompress\s*$", text, re.M), "must delaycompress"


def test_logrotate_tolerates_missing_and_empty_logs():
	text = LOGROTATE_CONF.read_text()
	assert re.search(r"^\s*missingok\s*$", text, re.M), (
		"missingok: a host that has not served traffic yet must not error"
	)
	assert re.search(r"^\s*notifempty\s*$", text, re.M), "must not rotate empty logs"


def test_logrotate_recreates_logs_with_the_nginx_owner():
	# nginx reopens the path on USR1 and must be able to write it again.
	text = LOGROTATE_CONF.read_text()
	assert re.search(r"^\s*create\s+0640\s+www-data\s+adm\s*$", text, re.M), (
		"must recreate logs as 0640 www-data:adm so nginx can write them"
	)


def test_logrotate_uses_sharedscripts():
	# Two files match the glob; without sharedscripts the postrotate (and its
	# USR1) runs once per file.
	assert re.search(r"^\s*sharedscripts\s*$", LOGROTATE_CONF.read_text(), re.M)


def test_logrotate_postrotate_makes_nginx_reopen_its_logs():
	text = LOGROTATE_CONF.read_text()
	match = re.search(r"postrotate(.*?)endscript", text, re.S)
	assert match, "drop-in must have a postrotate script"
	body = match.group(1)
	# Without USR1 nginx keeps writing to the rotated inode: the live log stops
	# growing and the disk is never actually reclaimed.
	assert re.search(r"kill\s+-USR1", body), "postrotate must signal nginx to reopen logs"
	assert "nginx.pid" in body, "postrotate must signal the nginx master pid"


def test_logrotate_postrotate_cannot_fail_the_rotation():
	# logrotate treats a non-zero postrotate as an error for the whole set; a
	# stopped nginx (no pidfile) must not block rotation.
	text = LOGROTATE_CONF.read_text()
	match = re.search(r"postrotate(.*?)endscript", text, re.S)
	assert match
	body = match.group(1)
	assert "|| true" in body or re.search(r"if\s+\[", body), (
		"postrotate must be guarded so a stopped nginx cannot fail the rotation"
	)


# ── AC2: the deploy installs + validates the drop-in ───────────────────────


def test_deploy_syncs_logrotate_conf_to_server():
	text = DEPLOY_WORKFLOW.read_text()
	assert re.search(r"rsync.*(\n.*)*?logrotate/podcaststudiohub-nginx", text), (
		"deploy must rsync the logrotate drop-in to the server"
	)


def test_deploy_installs_logrotate_conf_to_logrotate_d():
	text = DEPLOY_WORKFLOW.read_text()
	assert LOGROTATE_INSTALL_PATH in text, (
		f"deploy must install the drop-in to {LOGROTATE_INSTALL_PATH}"
	)


def test_deploy_installs_logrotate_conf_idempotently():
	# Re-running the deploy must overwrite in place — never append or duplicate.
	step = _logrotate_step()
	install = re.search(r"install\s+-m\s+0644((?:[^\n]*\\\n)*[^\n]*)", step)
	assert install, "drop-in must be installed with `install -m 0644` (overwrite in place)"
	# The destination may be spelled literally or via a variable assigned to it.
	target = install.group(1)
	assert LOGROTATE_INSTALL_PATH in target or re.search(r"\$\{?DEST\b", target), (
		f"the `install` must target {LOGROTATE_INSTALL_PATH}"
	)
	assert LOGROTATE_INSTALL_PATH in step, "the install path must appear in the step"
	assert ">>" not in step, "must not append to the drop-in (not idempotent)"


def test_deploy_validates_logrotate_conf_before_it_can_break_rotation():
	# `logrotate -d` is a parse-only dry run: a malformed drop-in must fail the
	# deploy, not silently sit in /etc/logrotate.d breaking every daily run.
	step = _logrotate_step()
	assert re.search(r"logrotate\s+-d\b", step), "deploy must validate with `logrotate -d`"
	assert "set -e" in step, "the logrotate SSH block must fail fast on a bad config"


def test_deploy_logrotate_validation_catches_silently_ignored_directives():
	# Verified against real logrotate 3.21: `logrotate -d` exits 0 on an unknown
	# option — it prints "error: ... unknown option 'x' -- ignoring line" and
	# carries on. So `set -e` alone CANNOT catch a typo'd directive (e.g.
	# `rotat 14`), which would silently drop that setting. The step must inspect
	# the output for error lines, not just trust the exit status.
	step = _logrotate_step()
	assert re.search(r"grep[^\n]*error", step, re.I), (
		"validation must grep logrotate's output for 'error:' lines — its exit "
		"status is 0 for unknown/ignored directives"
	)


def test_deploy_does_privileged_logrotate_install_non_interactively():
	# The deploy account is the non-root service user (harden-host.sh), so
	# /etc/logrotate.d needs sudo — and `-n` fails loudly rather than hanging
	# forever on a password prompt.
	step = _logrotate_step()
	assert "sudo -n" in step, "privileged install must use non-interactive sudo (sudo -n)"


def test_deploy_ssh_heredocs_contain_no_backticks():
	# Found the hard way while adding the steps above: these are UNQUOTED
	# heredocs (<< EOF), so the *runner's* shell command-substitutes backticks
	# before the text is ever sent to the server — including backticks inside
	# '#' comments. A markdown-style comment like `pm2 install` therefore RUNS
	# pm2 install on the runner and is stripped from what the server receives.
	# Quoting the heredoc would break the intentional $SERVER_PATH expansion, so
	# the rule is simply: no backticks inside these bodies.
	text = DEPLOY_WORKFLOW.read_text()
	bodies = re.findall(r"<< EOF\n(.*?)\n\s*EOF$", text, re.S | re.M)
	assert bodies, "expected unquoted SSH heredocs in deploy-dev.yml"
	for body in bodies:
		assert "`" not in body, (
			"backtick inside an unquoted SSH heredoc: the runner will execute it "
			"as a command substitution instead of sending it to the server.\n"
			f"Offending block:\n{body[:400]}"
		)


def _logrotate_step() -> str:
	"""The nginx-logrotate workflow step body."""
	text = DEPLOY_WORKFLOW.read_text()
	match = re.search(r"- name: Install nginx log rotation\n(.*?)\n      - name:", text, re.S)
	assert match, "expected an 'Install nginx log rotation' step in deploy-dev.yml"
	return match.group(1)


# ── AC3: pm2-logrotate ─────────────────────────────────────────────────────


def _pm2_logrotate_step() -> str:
	text = DEPLOY_WORKFLOW.read_text()
	match = re.search(r"- name: Configure PM2 log rotation\n(.*?)\n      - name:", text, re.S)
	assert match, "expected a 'Configure PM2 log rotation' step in deploy-dev.yml"
	return match.group(1)


def test_deploy_installs_pm2_logrotate_module():
	assert "pm2 install pm2-logrotate" in _pm2_logrotate_step(), (
		"deploy must install the pm2-logrotate module (~/.pm2/logs is unrotated)"
	)


def test_deploy_configures_pm2_logrotate_retention():
	step = _pm2_logrotate_step()
	assert "pm2 set pm2-logrotate:max_size 10M" in step
	assert "pm2 set pm2-logrotate:retain 7" in step
	assert "pm2 set pm2-logrotate:compress true" in step
	assert "pm2 set pm2-logrotate:rotateInterval '0 0 * * *'" in step


def test_pm2_logrotate_configured_before_the_processes_start():
	# It is a global pm2 module: configure it once, before the API/frontend/
	# celery processes start writing logs under it.
	text = DEPLOY_WORKFLOW.read_text()
	configure = text.find("- name: Configure PM2 log rotation")
	first_start = text.find("pm2 start uv")
	assert configure != -1 and first_start != -1
	assert configure < first_start, (
		"pm2-logrotate must be configured before the first pm2 process starts"
	)


# ── AC4: documented policy ─────────────────────────────────────────────────


def test_readme_documents_log_rotation_policy():
	text = README.read_text()
	assert "Log rotation" in text, "README must have a log rotation section"
	assert "pm2-logrotate" in text, "README must document PM2 log rotation"
	assert LOGROTATE_INSTALL_PATH in text, "README must document where the drop-in installs"


def test_readme_documents_where_logs_live():
	text = README.read_text()
	assert "/opt/podcaststudiohub/logs" in text, "README must say where the nginx logs live"
	assert "~/.pm2/logs" in text, "README must say where the PM2 logs live"


def test_readme_states_retention_windows():
	text = README.read_text()
	rotation = text.find("## Log rotation")
	assert rotation != -1
	window = text[rotation : rotation + 3000]
	assert "14" in window, "README must state the nginx retention window"
	assert "7" in window and "10M" in window, "README must state the PM2 retention/size caps"
