#!/usr/bin/env bash
# provision-ssl.sh — Obtain Let's Encrypt TLS certificates and enable HTTPS for
# the Podcastfy Studio nginx site (issue #208).
#
# Idempotent: if a valid cert already exists for the domain it is left in place
# and only the nginx site config + auto-renewal are (re)installed.
#
# Run on the production/dev VPS as root (or via sudo):
#   sudo DOMAIN=dev.podcaststudiohub.me deployment/scripts/provision-ssl.sh
#
# Optional env overrides:
#   DOMAIN        — FQDN to issue the cert for (default: dev.podcaststudiohub.me)
#   EMAIL         — Let's Encrypt recovery email    (default: admin@<DOMAIN>)
#   API_PORT      — FastAPI upstream port           (default: 8005)
#   FRONTEND_PORT — Next.js upstream port           (default: 3010)
# Port defaults must match the committed deployment/nginx/podcastfy.conf —
# deployment/tests/test_port_alignment.py enforces this (issue #317).
#
# Prerequisites:
#   - DNS for $DOMAIN points at this server
#   - Port 80 reachable from the internet (Let's Encrypt HTTP-01 challenge)
#   - nginx installed (scripts/repo-maintainer/setup-demo-vps.sh covers this)
set -euo pipefail

DOMAIN="${DOMAIN:-dev.podcaststudiohub.me}"
API_PORT="${API_PORT:-8005}"
FRONTEND_PORT="${FRONTEND_PORT:-3010}"
WEBROOT="/var/www/html"
EMAIL="${EMAIL:-admin@${DOMAIN}}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE_CONF="${REPO_ROOT}/deployment/nginx/podcastfy.conf"
LOGROTATE_CONF="${REPO_ROOT}/deployment/logrotate/podcaststudiohub-nginx"
LOGROTATE_DEST="/etc/logrotate.d/podcaststudiohub-nginx"
SITE_NAME="podcastfy"
NGINX_SITE="/etc/nginx/sites-available/${SITE_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

log() { echo "[provision-ssl] $*"; }

# ── 1. Certbot ────────────────────────────────────────────────────────────
log "Checking certbot..."
if ! command -v certbot >/dev/null 2>&1; then
	log "Installing certbot..."
	apt-get update -qq
	apt-get install -y -qq certbot python3-certbot-nginx
else
	log "certbot already installed ($(certbot --version 2>&1))"
fi

mkdir -p "${WEBROOT}"

# ── 2. Bootstrap HTTP-only nginx (so the ACME challenge can be served) ─────
# The full repo config references not-yet-existing cert files, so nginx would
# refuse to start. Use a minimal HTTP-only config that only serves the
# acme-challenge webroot long enough to issue the certificate.
if [ ! -f "${CERT_DIR}/fullchain.pem" ] || [ ! -f "${CERT_DIR}/privkey.pem" ] || \
	! openssl x509 -checkend 2592000 -noout -in "${CERT_DIR}/fullchain.pem" >/dev/null 2>&1; then
	log "No usable cert for ${DOMAIN} — installing bootstrap HTTP-only config to serve the ACME challenge."

	# Back up any existing site config so a certbot failure restores it (via
	# the ERR trap below) rather than leaving the HTTP-only bootstrap active.
	backup_path=""
	if [ -f "${NGINX_SITE}" ]; then
		backup_path="$(mktemp)"
		cp -a "${NGINX_SITE}" "${backup_path}"
	fi
	restore_on_error() {
		if [ -n "${backup_path:-}" ] && [ -f "${backup_path}" ]; then
			log "certbot failed — restoring previous nginx config."
			cp -a "${backup_path}" "${NGINX_SITE}"
			nginx -t && systemctl reload nginx || true
			rm -f "${backup_path}"
		fi
	}
	trap restore_on_error ERR

	rm -f /etc/nginx/sites-enabled/default
	cat > "${NGINX_SITE}" <<HTTP
server {
	listen 80;
	server_name ${DOMAIN};
	location /.well-known/acme-challenge/ { root ${WEBROOT}; }
	location / { return 200 'provisioning SSL\n'; add_header Content-Type text/plain; }
}
HTTP
	ln -sf "${NGINX_SITE}" "${NGINX_ENABLED}"
	nginx -t
	systemctl reload nginx || systemctl restart nginx

	# ── 3. Obtain the certificate (webroot, non-interactive) ───────────────
	log "Obtaining certificate for ${DOMAIN} (email=${EMAIL})..."
	certbot certonly --webroot -w "${WEBROOT}" \
		-d "${DOMAIN}" \
		--email "${EMAIL}" \
		--agree-tos --no-eff-email \
		--non-interactive

	trap - ERR
	[ -n "${backup_path:-}" ] && [ -f "${backup_path}" ] && rm -f "${backup_path}"
else
	log "Certificate already exists at ${CERT_DIR} — skipping issuance."
fi

# ── 4. Install the full HTTPS config from the repo ────────────────────────
log "Installing repo nginx config (TLS + security headers) -> ${NGINX_SITE}"
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
mkdir -p /opt/podcaststudiohub/logs
cp -a "${SITE_CONF}" "${NGINX_SITE}"
# Honour the DOMAIN override: substitute the hardcoded host in the installed
# copy so server_name + cert paths match the certificate that was issued.
if [ "${DOMAIN}" != "dev.podcaststudiohub.me" ]; then
	sed -i "s/dev\.podcaststudiohub\.me/${DOMAIN}/g" "${NGINX_SITE}"
fi
# Honour port overrides the same way: rewrite the conf's committed dev
# defaults (8005/3010) to this environment's upstream ports.
if [ "${API_PORT}" != "8005" ]; then
	sed -i "s/127\.0\.0\.1:8005/127.0.0.1:${API_PORT}/g" "${NGINX_SITE}"
fi
if [ "${FRONTEND_PORT}" != "3010" ]; then
	sed -i "s/127\.0\.0\.1:3010/127.0.0.1:${FRONTEND_PORT}/g" "${NGINX_SITE}"
fi
ln -sf "${NGINX_SITE}" "${NGINX_ENABLED}"
rm -f /etc/nginx/sites-enabled/default

log "Validating nginx config..."
nginx -t

# ── 4b. Rotate the custom nginx logs ──────────────────────────────────────
# The site config above logs to /opt/podcaststudiohub/logs/ (the directory this
# script just created), which the distro's stock /etc/logrotate.d/nginx does NOT
# cover — it only globs /var/log/nginx/*.log. Unrotated, those files grow until
# they fill the VPS disk, which takes Postgres and the app down with it, not
# just nginx (issue #320).
#
# This lives here, not in the deploy workflow, for the same reason the site
# config does: /etc/logrotate.d is root-owned, and the deploy account is
# deliberately non-root (issue #209). Installing it per-deploy would mean
# granting that account passwordless root for a file that changes about once a
# year. Provisioning is already the root-run, operator-invoked step.
log "Installing nginx logrotate drop-in -> ${LOGROTATE_DEST}"

# Validate BEFORE installing: a malformed file in /etc/logrotate.d breaks the
# whole daily run, not just this entry.
#
# Exit status alone is NOT a sufficient gate — logrotate -d exits 0 on an
# unknown option (it prints "error: ... -- ignoring line" and carries on), so a
# typo like "rotat 14" would silently drop the retention window. Grep for error
# lines too. --state points at a throwaway file so the dry run cannot disturb
# the host's real logrotate state.
lr_state="$(mktemp)"
if ! lr_out="$(logrotate -d --state "${lr_state}" "${LOGROTATE_CONF}" 2>&1)"; then
	rm -f "${lr_state}"
	echo "${lr_out}" >&2
	log "logrotate rejected ${LOGROTATE_CONF} — refusing to install it."
	exit 1
fi
rm -f "${lr_state}"
if echo "${lr_out}" | grep -qi '^error:'; then
	echo "${lr_out}" >&2
	log "logrotate reported errors in ${LOGROTATE_CONF} — refusing to install it."
	exit 1
fi

# Idempotent: install overwrites in place, so re-running just refreshes it.
install -m 0644 -o root -g root "${LOGROTATE_CONF}" "${LOGROTATE_DEST}"
log "nginx log rotation installed (daily, keep 14, compressed)."

# ── 5. Auto-renewal ───────────────────────────────────────────────────────
log "Configuring auto-renewal (certbot.timer + nginx reload deploy-hook)..."
systemctl enable --now certbot.timer 2>/dev/null || true

deploy_hook="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh"
mkdir -p "$(dirname "${deploy_hook}")"
cat > "${deploy_hook}" <<'HOOK'
#!/usr/bin/env bash
# Reload nginx to pick up renewed Let's Encrypt certificates.
exec systemctl reload nginx
HOOK
chmod +x "${deploy_hook}"

log "Reloading nginx with the new TLS configuration..."
systemctl reload nginx

# ── 6. Verify ─────────────────────────────────────────────────────────────
log "Verifying renewal pipeline (dry-run)..."
certbot renew --dry-run

echo ""
log "Done. Verify in production with:"
echo "  curl -sIL http://${DOMAIN} | head -n 5"
echo "  curl -sI https://${DOMAIN} | grep -iE 'strict-transport-security|content-security-policy|x-frame-options|x-content-type-options|referrer-policy'"
echo "  nmap --script ssl-enum-ciphers -p 443 ${DOMAIN}"
