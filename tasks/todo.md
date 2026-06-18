# Issue #208 — fix(infra): nginx serves authenticated SaaS over plain HTTP

**Source**: self-authored (issue had no implementation plan)
**Severity**: P1 / blocker / area-security + area-deployment
**Branch**: `fix/208-nginx-tls-security-headers`

## Problem
`deployment/nginx/podcastfy.conf` ships with `listen 80;` only; the 443/SSL
block, the HTTP→HTTPS redirect, and every security header are commented out.
Yet `deployment/README.md` deploys under `https://dev.podcaststudiohub.me`.
Result: NextAuth session cookies / JWT bearer tokens traverse cleartext.

## Acceptance Criteria (from issue)
- [ ] AC1 — Obtain certs (Let's Encrypt), enable 443 server block + 301 redirect.
- [ ] AC2 — Add HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy;
      `ssl_protocols TLSv1.2 TLSv1.3` only.
- [ ] AC3 — Verify deployed domain actually serves over HTTPS.

## Adapted Plan (numbered steps)

### Step 1 — Test first (RED): `deployment/tests/test_nginx_config.py`
New pytest module that parses `deployment/nginx/podcastfy.conf` and asserts:
- A port-80 `server` block issues `return 301 https://$host$request_uri;`
- A `listen 443 ssl` server block exists
- `ssl_protocols TLSv1.2 TLSv1.3;` present, and no `TLSv1`/`TLSv1.1`/`SSLv3`
- All 5 headers: `Strict-Transport-Security`, `Content-Security-Policy`,
  `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- HSTS carries `max-age` (≥15552000) and `preload`
- Cert paths reference `/etc/letsencrypt/live/`
- Fixture `nginx_syntax_ok`: runs `nginx -t` inside the official `nginx:stable`
  Docker image (skipped if Docker unavailable) for real syntax validation

Files: `deployment/tests/test_nginx_config.py`, `deployment/tests/conftest.py`

### Step 2 — Rewrite `deployment/nginx/podcastfy.conf` (GREEN)
- `upstream podcastfy_api` (unchanged)
- Server `listen 80` → `return 301 https://$host$request_uri;`
- Server `listen 443 ssl http2;` with:
  - `server_name dev.podcaststudiohub.me;`
  - `ssl_certificate /etc/letsencrypt/live/dev.podcaststudiohub.me/fullchain.pem;`
    + `ssl_certificate_key .../privkey.pem;`
  - `ssl_protocols TLSv1.2 TLSv1.3;`, `ssl_ciphers` (strong), `ssl_session_*`,
    `ssl_prefer_server_ciphers on;`
  - Security headers via `add_header ... always` (HSTS w/ preload, CSP,
    X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy
    strict-origin-when-cross-origin)
  - `.well-known/acme-challenge` webroot location (cert renewal)
  - Preserve existing `/`, `/api/`, `/health`, `/static/`, hidden-file block,
    `client_max_body_size`
- Tabs for indentation (matches repo style)

### Step 3 — `deployment/scripts/provision-ssl.sh` (Let's Encrypt, idempotent)
Mirrors `scripts/repo-maintainer/setup-demo-vps.sh` conventions
(`#!/usr/bin/env bash`, `set -euo pipefail`, tabs, skip-if-present):
- Install certbot + `python3-certbot-nginx`
- Place + enable the nginx site (`sites-available`/`sites-enabled`)
- `certbot certonly --webroot -w /var/www/html -d $DOMAIN`
  (or `--nginx` fallback) — non-interactive, `--agree-tos`, `--no-eff-email`
- `certbot renew --dry-run` smoke check
- Enable the systemd `certbot.timer` for auto-renewal
- `nginx -t && systemctl reload nginx`
- `$DOMAIN` defaults to `dev.podcaststudiohub.me`, overridable via env

### Step 4 — CI job in `.github/workflows/test.yml`
Add `test-deployment` job (ubuntu, no services needed):
- `pip install pytest`
- `python -m pytest deployment/tests/`
- Real syntax check: `docker run --rm -v $PWD/deployment/nginx:/etc/nginx/conf.d:ro
  -v $PWD/deployment/tests/nginx-main.conf:/etc/nginx/nginx.conf:ro nginx:stable
  nginx -t` (the test's Docker fixture mirrors this)
- Wire into `quality-gate` `needs:` so a config regression blocks the PR

### Step 5 — Docs sync: `deployment/README.md`
- New "## SSL / TLS (Let's Encrypt)" section pointing at `provision-ssl.sh`
- Replace bare `scp` nginx note with the script-driven one-time setup
- Add HTTPS verification commands (`curl -sIL`, header check, `nmap --script
  ssl-enum-ciphers`)

## Test Strategy
| Criterion | Test |
|---|---|
| AC1 (443 + 301) | `test_http_redirects_to_https`, `test_https_server_block_exists` |
| AC2 (headers + TLS) | `test_security_headers_present`, `test_hsts_directive`, `test_tls_protocols` |
| AC2 (syntax) | `nginx_syntax_ok` Docker fixture |
| AC3 (verify HTTPS) | `provision-ssl.sh` + README verification commands |

## Deviations / Assumptions (self-authored)
- No plan existed on the issue; this plan is authored from the codebase.
- `server_name` + cert path hardcoded to `dev.podcaststudiohub.me` (matches the
  documented single deployment); overridable in the script via `$DOMAIN`.
- CSP uses `'unsafe-inline'` for `style-src` (Next.js runtime styles) and
  `script-src 'self' 'unsafe-inline'` to remain functional; nonce-hardening is
  documented as a Known Limitation in the PR (full nonce support is a follow-up).
- nginx config is NOT auto-deployed by `deploy-dev.yml` today (it's a manual
  scp); this PR keeps that boundary but adds CI validation so regressions are
  caught. Operational cert obtain/verify (AC1/AC3 execution) happens on the
  server via the new script — the PR ships the code + docs to do it.
