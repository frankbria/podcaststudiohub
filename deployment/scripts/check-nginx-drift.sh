#!/usr/bin/env bash
# Assert the nginx site config installed on the box matches the committed one
# (issue #491). Runs on the deploy runner as the deploy account — read-only.
#
# nginx is operator-installed as root from the root-owned clone (see
# deployment/README.md → "How the box gets deployment assets"), so the deploy
# never writes it. Nothing checked it either, which is how the dev box served a
# pre-#307 config — a stale 'unsafe-inline' CSP stacked on the middleware's
# nonce policy — for two months. This check is what makes committing the
# config mean something.
#
# Env: SSH_HOST, SSH_USER (required); DOMAIN, API_PORT, FRONTEND_PORT
# (optional — rendered into the committed file exactly as provision-ssl.sh
# renders them into the installed copy, so non-dev environments compare
# against their own rendering rather than the committed dev defaults).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE_CONF="${REPO_ROOT}/deployment/nginx/podcastfy.conf"
LIVE="/etc/nginx/sites-available/podcastfy"
DOMAIN="${DOMAIN:-dev.podcaststudiohub.me}"
API_PORT="${API_PORT:-8005}"
FRONTEND_PORT="${FRONTEND_PORT:-3010}"

: "${SSH_HOST:?SSH_HOST is required}"
: "${SSH_USER:?SSH_USER is required}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
expected="${work}/expected.conf"
live="${work}/live.conf"

# Same three rewrites provision-ssl.sh applies at install time.
cp "$SITE_CONF" "$expected"
if [ "${DOMAIN}" != "dev.podcaststudiohub.me" ]; then
	sed -i "s/dev\.podcaststudiohub\.me/${DOMAIN}/g" "$expected"
fi
if [ "${API_PORT}" != "8005" ]; then
	sed -i "s/127\.0\.0\.1:8005/127.0.0.1:${API_PORT}/g" "$expected"
fi
if [ "${FRONTEND_PORT}" != "3010" ]; then
	sed -i "s/127\.0\.0\.1:3010/127.0.0.1:${FRONTEND_PORT}/g" "$expected"
fi

# Fetch first, diff second: an SSH failure must read as "could not fetch",
# not as drift.
# shellcheck disable=SC2029  # ${LIVE} expanding client-side is the point
ssh "${SSH_USER}@${SSH_HOST}" "cat ${LIVE}" > "$live"

if diff -u --label "${LIVE} (live on the deploy host)" \
	--label "deployment/nginx/podcastfy.conf (committed, rendered)" \
	"$live" "$expected"; then
	echo "✓ nginx config on the deploy host matches deployment/nginx/podcastfy.conf"
	exit 0
fi

cat >&2 <<EOF

❌ nginx config drift (issue #491): ${LIVE} on the deploy host does not match
   deployment/nginx/podcastfy.conf. The box serves what is installed, not what
   is committed. Re-sync as root from the root-owned clone:

     sudo git -C /root/podcaststudiohub pull
     sudo cp /root/podcaststudiohub/deployment/nginx/podcastfy.conf ${LIVE}
     sudo nginx -t && sudo systemctl reload nginx

   (deployment/README.md → "To update the Nginx config")
EOF
exit 1
