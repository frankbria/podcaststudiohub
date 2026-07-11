# Podcastfy Studio Hub - Deployment Guide

## Overview

This application deploys to **<SERVER_IP>** at `/opt/podcaststudiohub/` using **PM2** for process management.

## Host Hardening (non-root + firewall) — issue #209

Services run under a **dedicated non-root service account** (`podcastfy`), the API
binds **127.0.0.1 only** (nginx reverse-proxies to it), and a host firewall blocks
direct external access. Provision this once on the VPS:

```bash
ssh root@<SERVER_IP>
cd /opt/podcaststudiohub && bash deployment/scripts/harden-host.sh
```

`harden-host.sh` (idempotent):
1. Creates the `podcastfy` system account and an `~/.ssh` dir for the deploy key.
2. Stops any root-owned PM2 services (releasing ports 8005/3010) and installs a
   boot-time PM2 resurrect unit for the `podcastfy` account so services survive reboots.
3. Chowns `/opt/podcaststudiohub` to that account.
4. Configures `ufw`: default-deny inbound, allow only OpenSSH / 80 / 443.

After running it, **add the deploy public key** to
`/home/podcastfy/.ssh/authorized_keys` and **set the GitHub `SERVER_USER` deploy
secret to `podcastfy`** so PM2 processes start under the non-root account on the
next deploy. The API binds loopback (`API_HOST=127.0.0.1`, port `8005` on the
current dev host — matching that host's nginx upstream; see Environment Variables
below) and runs with `DEBUG=False` (uvicorn auto-reload stays off in prod).

## Deployment Methods

### 1. Automated Deployment (Recommended)

**GitHub Actions automatically deploys when code is pushed to `main`.**

The workflow is defined in `.github/workflows/deploy-dev.yml` and:
- ✅ Runs tests (API + Frontend)
- ✅ Builds frontend with Next.js
- ✅ Syncs code to server via rsync
- ✅ Installs dependencies with `uv` (API) and `npm` (frontend)
- ✅ Runs database migrations
- ✅ Restarts PM2 processes
- ✅ Performs health checks

**To trigger deployment:**
```bash
git push origin main
```

**To deploy manually without tests:**
1. Go to **Actions** tab in GitHub
2. Select **Deploy to Development** workflow
3. Click **Run workflow**
4. Check **Skip tests** if needed
5. Click **Run workflow**

### 2. Manual Deployment

If you need to deploy manually (parallel to GitHub Actions workflow):

#### Prerequisites
- SSH access to server: `ssh root@<SERVER_IP>`
- Server has PM2 installed globally
- Server has `uv` installed for Python dependencies

#### Step 1: Build Frontend Locally

```bash
cd apps/web
npm ci
npm run build
cd ../..
```

#### Step 2: Deploy API

```bash
# Sync API source
rsync -avz --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.venv' \
  apps/api/src/ root@<SERVER_IP>:/opt/podcaststudiohub/api/src/

# Sync API config
rsync -avz apps/api/pyproject.toml apps/api/uv.lock apps/api/alembic.ini \
  root@<SERVER_IP>:/opt/podcaststudiohub/api/

# Sync migrations
rsync -avz --exclude='__pycache__' --exclude='*.pyc' \
  apps/api/alembic/ root@<SERVER_IP>:/opt/podcaststudiohub/api/alembic/

# Install dependencies and run migrations on server
ssh root@<SERVER_IP> << 'EOF'
cd /opt/podcaststudiohub/api
uv sync
# Migrations MUST run under the privileged role (issue #301): MIGRATION_DATABASE_URL
# (set in .env) points Alembic at the superuser/BYPASSRLS owner so RLS-affected
# backfills apply to all rows. The app keeps connecting as the non-privileged
# podcastfy_app via DATABASE_URL. Without it, migrations fail loudly rather than
# silently no-op the backfills.
uv run alembic upgrade head

# Clear Python cache
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find . -type f -name '*.pyc' -delete 2>/dev/null || true

# Restart API
pm2 delete podcaststudiohub-api 2>/dev/null || true
pm2 start uv --name podcaststudiohub-api --cwd /opt/podcaststudiohub/api \
  -- run uvicorn src.main:app --host 127.0.0.1 --port 8005
pm2 save
EOF
```

#### Step 3: Deploy Frontend

```bash
# Sync public files
rsync -avz apps/web/public/ root@<SERVER_IP>:/opt/podcaststudiohub/frontend/public/

# Sync source files
rsync -avz apps/web/src/ root@<SERVER_IP>:/opt/podcaststudiohub/frontend/src/

# Sync config files
rsync -avz apps/web/package.json apps/web/next.config.mjs apps/web/tsconfig.json \
  apps/web/tailwind.config.ts apps/web/postcss.config.mjs \
  root@<SERVER_IP>:/opt/podcaststudiohub/frontend/

# Install dependencies and rebuild on server
ssh root@<SERVER_IP> << 'EOF'
cd /opt/podcaststudiohub/frontend

# Create environment file
cat > .env.production << 'ENVEOF'
NEXT_PUBLIC_API_URL=https://dev.podcaststudiohub.me/api
NEXTAUTH_SECRET=<your-secret>
NEXTAUTH_URL=https://dev.podcaststudiohub.me
PORT=3010
ENVEOF

# Install and build
npm ci
npm run build

# Update runtime config
echo "window.__ENV__ = { API_URL: 'https://dev.podcaststudiohub.me/api' };" > public/config.js

# Restart frontend
pm2 delete podcaststudiohub-frontend 2>/dev/null || true
PORT=3010 \
NEXT_PUBLIC_API_URL='https://dev.podcaststudiohub.me/api' \
NEXTAUTH_SECRET='<your-secret>' \
NEXTAUTH_URL='https://dev.podcaststudiohub.me' \
pm2 start npm --name podcaststudiohub-frontend --cwd /opt/podcaststudiohub/frontend -- start
pm2 save
EOF
```

#### Step 4: Restart Celery

`-B` runs beat embedded in this single worker process — no separate process
starts a standalone beat, so without it nothing actually schedules
`reap_stuck_episodes` or `drain_storage_deletion_outbox` (issue #366). This is
only safe with exactly one worker process; running `-B` on more than one would
double-schedule every beat task.

```bash
ssh root@<SERVER_IP> << 'EOF'
cd /opt/podcaststudiohub/api

pm2 delete podcaststudiohub-celery 2>/dev/null || true
pm2 start uv --name podcaststudiohub-celery --cwd /opt/podcaststudiohub/api \
  -- run celery -A src.worker:celery_app worker -B --loglevel=info
pm2 save
EOF
```

#### Step 5: Verify Deployment

```bash
# Check PM2 processes
ssh root@<SERVER_IP> "pm2 list"

# Check API health
curl https://dev.podcaststudiohub.me/api/health

# Check frontend
curl https://dev.podcaststudiohub.me
```

## Server Structure

```
/opt/podcaststudiohub/
├── api/                    # FastAPI backend
│   ├── .venv/             # Python virtual env (created by uv)
│   ├── src/               # Source code
│   ├── alembic/           # Database migrations
│   ├── pyproject.toml     # Python dependencies
│   └── .env               # Environment variables (not in git)
│
└── frontend/              # Next.js frontend
    ├── .next/             # Built Next.js files
    ├── node_modules/      # Node dependencies
    ├── src/               # Source code
    ├── public/            # Static files
    ├── package.json       # Node dependencies
    └── .env.production    # Environment variables (not in git)
```

## PM2 Processes

**View all processes:**
```bash
ssh root@<SERVER_IP> "pm2 list"
```

**Check logs:**
```bash
ssh root@<SERVER_IP> "pm2 logs podcaststudiohub-api --lines 50"
ssh root@<SERVER_IP> "pm2 logs podcaststudiohub-frontend --lines 50"
ssh root@<SERVER_IP> "pm2 logs podcaststudiohub-celery --lines 50"
```

**Restart individual service:**
```bash
ssh root@<SERVER_IP> "pm2 restart podcaststudiohub-api"
ssh root@<SERVER_IP> "pm2 restart podcaststudiohub-frontend"
ssh root@<SERVER_IP> "pm2 restart podcaststudiohub-celery"
```

**Restart all:**
```bash
ssh root@<SERVER_IP> "pm2 restart all"
```

## Environment Variables

### GitHub Secrets/Variables

Configure in **Settings** → **Environments** → **development**:

**Variables:**
- `SERVER_HOST`: `<SERVER_IP>`
- `SERVER_PATH`: `/opt/podcaststudiohub`
- `API_URL`: `https://dev.podcaststudiohub.me/api`
- `FRONTEND_URL`: `https://dev.podcaststudiohub.me`
- `NEXTAUTH_URL`: `https://dev.podcaststudiohub.me`
- `API_PORT`: `8005`
- `FRONTEND_PORT`: `3010`

> The dev host is **multi-tenant** (several apps share it), so these ports are
> per-environment, not repo-wide constants. `API_PORT`/`FRONTEND_PORT` are the
> source of truth and **must match that host's nginx upstream**
> (`/etc/nginx/sites-available/podcaststudiohub` on the server). The values in
> `deployment/nginx/podcastfy.conf` (8001/3003) are a single-tenant example.

**Secrets:**
- `SSH_PRIVATE_KEY`: SSH key for deployment
- `SERVER_USER`: `podcastfy` (the dedicated non-root service account created by
  `harden-host.sh` — see **Host Hardening** above; do **not** deploy as root)
- `NEXTAUTH_SECRET`: Generated with `openssl rand -base64 32`

### Server Environment Files

**API (`/opt/podcaststudiohub/api/.env`):**
```bash
# App role: non-privileged podcastfy_app (FORCE RLS enforced). The app requires
# the asyncpg driver prefix (see apps/api/src/database.py).
DATABASE_URL=postgresql+asyncpg://podcastfy_app:pass@localhost/podcastfy
# Alembic-only privileged role (superuser/BYPASSRLS owner) — required so RLS-affected
# backfills apply to all rows (issue #301). Falls back to DATABASE_URL when unset.
MIGRATION_DATABASE_URL=postgresql+asyncpg://podcastfy:pass@localhost/podcastfy
# Secret password for the podcastfy_app role (issue #304). Alembic reads it at
# migration time: migration 014 rotates the role password to this value whenever
# it is set (fresh installs use it in 003). Generate with `openssl rand -hex 32`
# and keep it in sync with the password embedded in DATABASE_URL above.
APP_DB_PASSWORD=<same-password-as-in-DATABASE_URL>
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=<generate-with-openssl-rand-hex-32>
JWT_ALGORITHM=HS256
ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>
DEBUG=False
LOG_LEVEL=INFO

# Optional - users can provide their own
OPENAI_API_KEY=
GEMINI_API_KEY=
ELEVENLABS_API_KEY=
TRANSISTOR_API_KEY=

# AWS S3 (audio storage) - see "AWS S3 / IAM permissions" below
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=podcaststudiohub-audio
AWS_REGION=us-east-1
```

> Keep real secrets out of version control: these `.env` files are gitignored and must never be
> committed. A `gitleaks` pre-commit hook (repo root `.pre-commit-config.yaml`) blocks accidental
> commits of keys.

**Frontend (`/opt/podcaststudiohub/frontend/.env.production`):**
```bash
NEXT_PUBLIC_API_URL=https://dev.podcaststudiohub.me/api
NEXTAUTH_URL=https://dev.podcaststudiohub.me
NEXTAUTH_SECRET=<same-as-github-secret>
PORT=3010
```

### AWS S3 / IAM permissions

The API stores generated audio in S3 (`AWS_S3_BUCKET`, default `podcaststudiohub-audio`) using a
dedicated IAM user (e.g. `fastapi-s3-uploader`). That user needs an identity-based policy granting
**object-level** access only — the app never lists the bucket:

| Action | Why |
|---|---|
| `s3:PutObject` | upload generated audio (incl. multipart for large/long-form files) |
| `s3:GetObject` | download / `head_object` / presigned playback URLs |
| `s3:DeleteObject` | remove audio when an episode or account is deleted |
| `s3:AbortMultipartUpload` | clean up failed multipart uploads |

`s3:ListBucket` is intentionally **not** granted (least privilege). `aws s3 ls` returns
`AccessDenied` for this user *by design* — that is expected, not a misconfiguration.

Minimal inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PodcastAudioObjectRW",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:AbortMultipartUpload"],
      "Resource": "arn:aws:s3:::podcaststudiohub-audio/*"
    }
  ]
}
```

Apply it from AWS CloudShell (which runs as your admin console identity):

```bash
aws iam put-user-policy --user-name fastapi-s3-uploader \
  --policy-name podcast-audio-object-rw --policy-document file://s3-policy.json
```

**Rotating the access key:** AWS keys can't be edited in place. Create a new key → update `.env`
here and on the dev machine → `pm2 restart podcaststudiohub-api` → verify (PutObject/GetObject/
DeleteObject) → **then** deactivate and delete the old key. Permissions live on the IAM user, not
the key, so rotation never changes them.

**Enable bucket versioning (required):** versioning protects generated audio against accidental
overwrite/delete. The app's least-privilege IAM user *cannot* toggle versioning, so this is a
one-time **administrative** action — run it from AWS CloudShell (admin identity), not the app user:

```bash
deployment/scripts/enable-s3-versioning.sh podcaststudiohub-audio
```

### Tenant offboarding / GDPR erasure — issue #308

`DELETE /auth/me` (authenticated, self-service — the app has no admin/superuser role) permanently
erases a user's account:

- **Postgres rows**: the user row is deleted directly; every other tenant-owned row (projects,
  episodes, episode compositions, audio snippets, RSS feeds, content sources, distribution targets,
  templates, TTS configs, layouts, team memberships/invitations, and billing
  subscription/usage rows — whose FKs exist in migration 010 even though the ORM models omit
  them) cascades via `ON DELETE CASCADE`.
- **Guards**: the request must re-enter the account password (step-up auth; 403 on mismatch), and
  erasure is refused with 409 while any episode is mid-generation — the running Celery chain would
  re-upload audio to S3 after cleanup, recreating the orphaned-object problem this issue fixed.
- **S3 objects**: deleted by the keys already stored on those rows (`episodes.s3_key`,
  `episode_compositions.composed_s3_key`, `audio_snippets.s3_key`, `rss_feeds.s3_key`, and the
  `s3_key` inside `content_sources.source_data`). This is why `s3:ListBucket` is never needed — see
  above.
- **Local file artifacts**: episode audio/transcript files, composed audio, and snippet audio are
  removed from disk.

Storage and filesystem cleanup are **best-effort**: a failed S3 or `os.remove` call is logged but
never blocks the Postgres erasure, matching the same pattern single-episode delete uses (below).

Single-episode `DELETE /episodes/{id}` follows the same best-effort pattern at smaller scope: it
removes the episode's `s3_key`, its composition's `composed_s3_key`, and the episode's local
audio/transcript files, but does not touch that episode's content-source uploads (those are only
erased on full account deletion).

**Known limitations** (disclosed, not yet addressed):

- `Team` rows have no owner; erasure removes the user's own memberships/invitations but leaves team
  shells behind.
- Stripe-side customer data is untouched — only local billing rows are deleted. Cancelling the
  Stripe subscription/customer is out of scope here.

## Database Backup & Restore (DR) — issue #293

All durable tenant state (accounts, projects, episodes, RSS feeds, distribution
targets with encrypted OAuth tokens, Stripe billing) lives only in the VPS
Postgres datadir. Host loss without an off-host copy = total, unrecoverable loss.
These scripts give an automated nightly logical dump shipped to S3 with retention,
plus a tested restore path.

**Recovery targets:** **RPO ≤ 24h** (worst case: data written since the last
nightly dump) and **RTO ≈ minutes** (download the dump + `pg_restore`). For a
tighter RPO you'd move to continuous WAL archiving (pgBackRest/WAL-G); nightly
logical dumps are the deliberate, lazy-correct choice for a single-VPS dev host.

### What it does

- `deployment/scripts/backup-db.sh` — `pg_dump -Fc` → timestamped object
  at `s3://$DB_BACKUP_S3_BUCKET/$DB_BACKUP_S3_PREFIX`, then prunes objects older
  than `DB_BACKUP_RETENTION_DAYS` (default 14).
- `deployment/scripts/install-db-backup-timer.sh` — installs a systemd service +
  nightly timer (`03:30` by default) that runs the backup as the non-root
  `podcastfy` service account, reading DB/S3 settings from the API `.env`.
- `deployment/scripts/restore-db.sh` — pulls a dump from S3 and `pg_restore`s it
  (latest by default, or a named backup), guarded by a confirmation prompt.

Settings (env, defaulting to the app's existing `AWS_*` / `DATABASE_URL`):

| Var | Default | Meaning |
|---|---|---|
| `DB_BACKUP_S3_BUCKET` | `$AWS_S3_BUCKET` | bucket for dumps |
| `DB_BACKUP_S3_PREFIX` | `db-backups/` | key prefix |
| `DB_BACKUP_RETENTION_DAYS` | `14` | prune objects older than N days |
| `ON_CALENDAR` (installer) | `*-*-* 03:30:00` | systemd nightly schedule |

> **IAM:** the backup needs `s3:PutObject` + `s3:GetObject` + `s3:DeleteObject`
> (retention prune) **and** `s3:ListBucket` (find latest / prune) on the backup
> prefix. The app's audio IAM user intentionally lacks `ListBucket`, so use a
> separate backup credential, or set `DB_BACKUP_S3_BUCKET` to a dedicated bucket
> whose IAM policy grants those four actions on `arn:aws:s3:::<bucket>/db-backups/*`
> plus `ListBucket` on the bucket.

### Install (once, on the VPS)

```bash
ssh root@<SERVER_IP>
cd /opt/podcaststudiohub && bash deployment/scripts/install-db-backup-timer.sh
systemctl list-timers podcastfy-db-backup.timer   # confirm the next run
```

Trigger an immediate backup to verify the pipeline end-to-end:

```bash
systemctl start podcastfy-db-backup.service
journalctl -u podcastfy-db-backup.service -n 50    # look for "Uploaded … to s3://…"
aws s3 ls s3://$AWS_S3_BUCKET/db-backups/           # the dump object is present
```

### Restore runbook (tested)

```bash
ssh root@<SERVER_IP>
cd /opt/podcaststudiohub

# Make DB/S3 settings available (same as the app):
set -a && . api/.env && set +a

# Restore the latest backup (prompts before overwriting):
bash deployment/scripts/restore-db.sh

# …or a specific backup by name:
aws s3 ls s3://$AWS_S3_BUCKET/db-backups/
bash deployment/scripts/restore-db.sh podcastfy-20260601T033000Z.dump
```

**Test the restore without touching prod** (do this at least once, then quarterly):

```bash
# Restore the latest dump into a throwaway database and sanity-check row counts.
createdb podcastfy_restore_test
DATABASE_URL="postgresql://user:pass@localhost/podcastfy_restore_test" \
  DB_RESTORE_FORCE=1 bash deployment/scripts/restore-db.sh
psql podcastfy_restore_test -c "SELECT count(*) FROM users;"
dropdb podcastfy_restore_test
```

A green restore-test is the only proof the backups are usable — an untested
backup is not a backup.

## Nginx Configuration

Nginx reverse proxy configuration is in `deployment/nginx/podcastfy.conf`.

**Routes:**
- `https://dev.podcaststudiohub.me/api` → `localhost:8005` (API)
- `https://dev.podcaststudiohub.me` → `localhost:3010` (Frontend)

The config terminates TLS 1.2/1.3 only and sends every request through a
301 HTTP→HTTPS redirect, plus HSTS / X-Frame-Options /
X-Content-Type-Options / Referrer-Policy. Port 80 never reaches the app.

The document Content-Security-Policy is **not** set by nginx: it is a
per-request nonce policy (no `'unsafe-inline'` script-src) minted by the
Next.js middleware (`apps/web/src/middleware.ts`, issue #307). Do not add a
CSP `add_header` back to the server block — browsers enforce the intersection
of multiple CSP headers, which would block every nonce'd script. The
`/static/` location keeps its own strict CSP for assets nginx serves
directly.

## SSL / TLS (Let's Encrypt)

Certificates are obtained and renewed with `deployment/scripts/provision-ssl.sh`.
Run it once on the VPS (idempotent — safe to re-run):

```bash
# Prerequisites: DNS for the domain points at the server, port 80 open.
scp -r deployment root@<SERVER_IP>:/opt/podcaststudiohub/deployment
ssh root@<SERVER_IP>
cd /opt/podcaststudiohub && DOMAIN=dev.podcaststudiohub.me \
  bash deployment/scripts/provision-ssl.sh
```

The script:
1. Installs certbot and issues a cert for `$DOMAIN` via the HTTP-01 webroot
   challenge (`/var/www/html/.well-known/acme-challenge/`).
2. Installs the repo's `podcastfy.conf` to `/etc/nginx/sites-available/podcastfy`
   and enables it (the cert paths point at `/etc/letsencrypt/live/<domain>/`).
3. Enables `certbot.timer` and a renewal deploy-hook that reloads nginx, so
   renewed certs are picked up automatically.
4. Runs `certbot renew --dry-run` to verify the renewal pipeline.

**Verify HTTPS is live** (acceptance criteria for the TLS rollout):
```bash
# HTTP must 301-redirect to HTTPS
curl -sIL http://dev.podcaststudiohub.me | head -n 5

# All security headers present
curl -sI https://dev.podcaststudiohub.me | grep -iE \
  'strict-transport-security|content-security-policy|x-frame-options|x-content-type-options|referrer-policy'

# Only TLS 1.2 / 1.3 offered
nmap --script ssl-enum-ciphers -p 443 dev.podcaststudiohub.me
```

**To update the Nginx config** (after editing `deployment/nginx/podcastfy.conf`):
```bash
scp deployment/nginx/podcastfy.conf root@<SERVER_IP>:/etc/nginx/sites-available/podcastfy
ssh root@<SERVER_IP> "nginx -t && systemctl reload nginx"
```

## Troubleshooting

### Deployment Failed in GitHub Actions

1. Check **Actions** tab for error logs
2. Common issues:
   - SSH connection failed → Verify `SSH_PRIVATE_KEY` secret
   - Health check failed → Check PM2 logs on server
   - Build failed → Check build errors in workflow logs

### Service Not Starting

```bash
# SSH to server
ssh root@<SERVER_IP>

# Check PM2 status
pm2 list
pm2 logs podcaststudiohub-api --lines 100

# Try restarting
pm2 restart podcaststudiohub-api
pm2 save
```

### Database Migration Issues

```bash
ssh root@<SERVER_IP> << 'EOF'
cd /opt/podcaststudiohub/api
uv run alembic current
uv run alembic history
uv run alembic upgrade head
EOF
```

### Clear All and Restart

```bash
ssh root@<SERVER_IP> << 'EOF'
cd /opt/podcaststudiohub/api
pm2 delete all
pm2 save --force

# Restart API
pm2 start uv --name podcaststudiohub-api --cwd /opt/podcaststudiohub/api \
  -- run uvicorn src.main:app --host 127.0.0.1 --port 8005

# Restart Frontend
cd /opt/podcaststudiohub/frontend
PORT=3010 pm2 start npm --name podcaststudiohub-frontend --cwd /opt/podcaststudiohub/frontend -- start

# Restart Celery (-B: embedded beat — single worker process only, see Step 4)
cd /opt/podcaststudiohub/api
pm2 start uv --name podcaststudiohub-celery --cwd /opt/podcaststudiohub/api \
  -- run celery -A src.worker:celery_app worker -B --loglevel=info

pm2 save
pm2 list
EOF
```

## GitHub Actions Workflow Details

See `.github/workflows/deploy-dev.yml` for the complete workflow.

See `.github/DEPLOYMENT_SETUP.md` for GitHub configuration instructions.

---

**Server**: <SERVER_IP>
**Path**: `/opt/podcaststudiohub/`
**Process Manager**: PM2
**Domain**: https://dev.podcaststudiohub.me
