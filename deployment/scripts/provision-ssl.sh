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
#   DOMAIN  — FQDN to issue the cert for (default: dev.podcaststudiohub.me)
#   EMAIL   — Let's Encrypt recovery email        (default: admin@<DOMAIN>)
#
# Prerequisites:
#   - DNS for $DOMAIN points at this server
#   - Port 80 reachable from the internet (Let's Encrypt HTTP-01 challenge)
#   - nginx installed (scripts/repo-maintainer/setup-demo-vps.sh covers this)
set -euo pipefail

DOMAIN="${DOMAIN:-dev.podcaststudiohub.me}"
WEBROOT="/var/www/html"
EMAIL="${EMAIL:-admin@${DOMAIN}}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE_CONF="${REPO_ROOT}/deployment/nginx/podcastfy.conf"
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
if [ ! -d "${CERT_DIR}" ]; then
	log "No cert yet for ${DOMAIN} — installing bootstrap HTTP-only config to serve the ACME challenge."
	rm -f /etc/nginx/sites-enabled/default
	cat > "${NGINX_SITE}" <<HTTP
upstream podcastfy_api { server 127.0.0.1:8001; }
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
else
	log "Certificate already exists at ${CERT_DIR} — skipping issuance."
fi

# ── 4. Install the full HTTPS config from the repo ────────────────────────
log "Installing repo nginx config (TLS + security headers) -> ${NGINX_SITE}"
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
mkdir -p /opt/podcaststudiohub/logs
cp -a "${SITE_CONF}" "${NGINX_SITE}"
ln -sf "${NGINX_SITE}" "${NGINX_ENABLED}"
rm -f /etc/nginx/sites-enabled/default

log "Validating nginx config..."
nginx -t

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
