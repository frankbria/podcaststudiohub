#!/usr/bin/env bash
#
# Install the nightly PostgreSQL backup as a systemd timer (issue #293).
#
# Creates a oneshot service that runs backup-db.sh as the non-root service
# account, plus a timer that fires nightly. Idempotent — re-running just
# rewrites the units and re-enables the timer. Run once as root on the VPS:
#
#   ssh root@<server>
#   cd /opt/podcaststudiohub && bash deployment/scripts/install-db-backup-timer.sh
#
# The backup's S3/DB settings are read from the API's .env at run time, so the
# same DATABASE_URL / AWS_* / DB_BACKUP_* values the app uses drive the backup.
#
# Configuration (env):
#   SERVICE_USER     account that runs the backup (default: podcastfy)
#   APP_ROOT         app tree root            (default: /opt/podcaststudiohub)
#   BACKUP_ENV_FILE  env file with DB/S3 settings (default: $APP_ROOT/api/.env)
#   ON_CALENDAR      systemd schedule         (default: *-*-* 03:30:00 nightly)

set -euo pipefail

SERVICE_USER="${SERVICE_USER:-podcastfy}"
APP_ROOT="${APP_ROOT:-/opt/podcaststudiohub}"
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-$APP_ROOT/api/.env}"
ON_CALENDAR="${ON_CALENDAR:-*-*-* 03:30:00}"
SCRIPT_PATH="$APP_ROOT/deployment/scripts/backup-db.sh"

if [[ "$(id -u)" -ne 0 ]]; then
	echo "install-db-backup-timer.sh must run as root (it writes systemd units)." >&2
	exit 1
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
	echo "backup script not found at $SCRIPT_PATH — deploy the repo first." >&2
	exit 1
fi

echo "Installing podcastfy-db-backup systemd service + timer..."

cat >/etc/systemd/system/podcastfy-db-backup.service <<EOF
[Unit]
Description=Podcastfy Studio nightly PostgreSQL backup to S3 (issue #293)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
# Load DB/S3 settings from the app env. '-' = don't fail if absent (the unit
# still runs; backup-db.sh errors clearly if required vars are missing).
EnvironmentFile=-${BACKUP_ENV_FILE}
ExecStart=/usr/bin/env bash ${SCRIPT_PATH}
EOF

cat >/etc/systemd/system/podcastfy-db-backup.timer <<EOF
[Unit]
Description=Run the Podcastfy Studio PostgreSQL backup nightly (issue #293)

[Timer]
OnCalendar=${ON_CALENDAR}
# Catch up if the VPS was asleep/off at the scheduled time.
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now podcastfy-db-backup.timer

echo
echo "Installed. Next run:"
systemctl list-timers podcastfy-db-backup.timer --no-pager || true
echo
echo "Run an immediate backup to verify:  systemctl start podcastfy-db-backup.service"
echo "Then check logs:                    journalctl -u podcastfy-db-backup.service -n 50"
