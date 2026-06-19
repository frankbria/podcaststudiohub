#!/usr/bin/env bash
#
# Host hardening for the Podcastfy Studio VPS (issue #209).
#
# Creates a dedicated non-root service account that owns the app tree and runs
# the PM2 processes, and configures a host firewall that only exposes SSH and
# the nginx HTTP(S) ports. The API itself binds 127.0.0.1, so the firewall is
# defense-in-depth against any service that drifts back to a public bind.
#
# Idempotent: safe to re-run. Run once as root on the VPS:
#
#   ssh root@<server>
#   cd /opt/podcaststudiohub && bash deployment/scripts/harden-host.sh
#
# After running, point the GitHub `SERVER_USER` deploy secret at $SERVICE_USER
# and re-run the deploy workflow so PM2 processes start under the new account.

set -euo pipefail

SERVICE_USER="${SERVICE_USER:-podcastfy}"
APP_ROOT="${APP_ROOT:-/opt/podcaststudiohub}"

if [[ "$(id -u)" -ne 0 ]]; then
	echo "harden-host.sh must run as root (it creates a user and edits the firewall)." >&2
	exit 1
fi

# ── 1. Dedicated non-root service account ──────────────────────────────────
if id "$SERVICE_USER" >/dev/null 2>&1; then
	echo "Service account '$SERVICE_USER' already exists."
else
	echo "Creating service account '$SERVICE_USER'..."
	# System account, no login shell beyond what PM2/ssh-deploy needs.
	useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
fi

# The deploy uses rsync+ssh, so the account needs an SSH dir for its key.
install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_USER" "/home/$SERVICE_USER/.ssh"
echo "Add the deploy public key to /home/$SERVICE_USER/.ssh/authorized_keys (chmod 600)."

# ── 2. Retire root-owned PM2 processes ─────────────────────────────────────
# PM2 is per-user: services first launched as root live in root's PM2 daemon
# and keep holding ports 8001/3003. The new $SERVICE_USER deploy can't see or
# stop them, so its uvicorn/next starts would fail on occupied ports. Stop and
# remove root's copies here (idempotent — no-op once they're gone).
if command -v pm2 >/dev/null 2>&1; then
	echo "Stopping any root-owned PM2 services (migrating to $SERVICE_USER)..."
	for svc in podcaststudiohub-api podcaststudiohub-frontend podcaststudiohub-celery; do
		pm2 delete "$svc" >/dev/null 2>&1 || true
	done
	pm2 save --force >/dev/null 2>&1 || true
	# Drop root's PM2 startup unit so it doesn't resurrect them on reboot...
	pm2 unstartup >/dev/null 2>&1 || true
	# ...and install one for the service account instead, so its API/frontend/
	# worker come back after a reboot (the deploy's `pm2 save` writes the dump
	# this unit resurrects). Without this, services stay down until a redeploy.
	# NOT suppressed: a failed startup unit silently breaks reboot persistence.
	pm2 startup systemd -u "$SERVICE_USER" --hp "/home/$SERVICE_USER"
fi

# ── 3. App tree ownership ──────────────────────────────────────────────────
if [[ -d "$APP_ROOT" ]]; then
	echo "Chowning $APP_ROOT to $SERVICE_USER..."
	chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_ROOT"
else
	echo "App root $APP_ROOT does not exist yet; creating it owned by $SERVICE_USER."
	install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$APP_ROOT"
fi

# ── 4. Host firewall (ufw) ─────────────────────────────────────────────────
if ! command -v ufw >/dev/null 2>&1; then
	echo "Installing ufw..."
	apt-get update -qq && apt-get install -y -qq ufw
fi

echo "Configuring firewall (default-deny inbound, allow SSH + HTTP/S)..."
# Reset first so any pre-existing allow rule (e.g. a directly-exposed 8000/8001
# from before this hardening) is cleared — otherwise it survives and stays open.
ufw --force reset
# Allow SSH FIRST and by port (22/tcp), not the "OpenSSH" app profile: the
# profile only exists if openssh-server registered it, and a missing profile
# under `set -e` would abort after default-deny — locking us out of the box.
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
# Non-interactive enable (no-op if already active).
ufw --force enable
ufw status verbose

echo
echo "Host hardening complete."
echo "Next: set the GitHub 'SERVER_USER' deploy secret to '$SERVICE_USER' and redeploy."
