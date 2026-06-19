# Podcastfy Studio Hub - Deployment Guide

## Overview

This application deploys to **47.88.89.175** at `/opt/podcaststudiohub/` using **PM2** for process management.

## Host Hardening (non-root + firewall) — issue #209

Services run under a **dedicated non-root service account** (`podcastfy`), the API
binds **127.0.0.1 only** (nginx reverse-proxies to it), and a host firewall blocks
direct external access. Provision this once on the VPS:

```bash
ssh root@47.88.89.175
cd /opt/podcaststudiohub && bash deployment/scripts/harden-host.sh
```

`harden-host.sh` (idempotent):
1. Creates the `podcastfy` system account and an `~/.ssh` dir for the deploy key.
2. Stops any root-owned PM2 services (releasing ports 8001/3003) and installs a
   boot-time PM2 resurrect unit for the `podcastfy` account so services survive reboots.
3. Chowns `/opt/podcaststudiohub` to that account.
4. Configures `ufw`: default-deny inbound, allow only OpenSSH / 80 / 443.

After running it, **add the deploy public key** to
`/home/podcastfy/.ssh/authorized_keys` and **set the GitHub `SERVER_USER` deploy
secret to `podcastfy`** so PM2 processes start under the non-root account on the
next deploy. The API binds loopback (`API_HOST=127.0.0.1`, port `8001` matching the
nginx upstream) and runs with `DEBUG=False` (uvicorn auto-reload stays off in prod).

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
- SSH access to server: `ssh root@47.88.89.175`
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
  apps/api/src/ root@47.88.89.175:/opt/podcaststudiohub/api/src/

# Sync API config
rsync -avz apps/api/pyproject.toml apps/api/uv.lock apps/api/alembic.ini \
  root@47.88.89.175:/opt/podcaststudiohub/api/

# Sync migrations
rsync -avz --exclude='__pycache__' --exclude='*.pyc' \
  apps/api/alembic/ root@47.88.89.175:/opt/podcaststudiohub/api/alembic/

# Install dependencies and run migrations on server
ssh root@47.88.89.175 << 'EOF'
cd /opt/podcaststudiohub/api
uv sync
uv run alembic upgrade head

# Clear Python cache
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find . -type f -name '*.pyc' -delete 2>/dev/null || true

# Restart API
pm2 delete podcaststudiohub-api 2>/dev/null || true
pm2 start uv --name podcaststudiohub-api --cwd /opt/podcaststudiohub/api \
  -- run uvicorn src.main:app --host 127.0.0.1 --port 8001
pm2 save
EOF
```

#### Step 3: Deploy Frontend

```bash
# Sync public files
rsync -avz apps/web/public/ root@47.88.89.175:/opt/podcaststudiohub/frontend/public/

# Sync source files
rsync -avz apps/web/src/ root@47.88.89.175:/opt/podcaststudiohub/frontend/src/

# Sync config files
rsync -avz apps/web/package.json apps/web/next.config.mjs apps/web/tsconfig.json \
  apps/web/tailwind.config.ts apps/web/postcss.config.mjs \
  root@47.88.89.175:/opt/podcaststudiohub/frontend/

# Install dependencies and rebuild on server
ssh root@47.88.89.175 << 'EOF'
cd /opt/podcaststudiohub/frontend

# Create environment file
cat > .env.production << 'ENVEOF'
NEXT_PUBLIC_API_URL=https://dev.podcaststudiohub.me/api
NEXTAUTH_SECRET=<your-secret>
NEXTAUTH_URL=https://dev.podcaststudiohub.me
PORT=3003
ENVEOF

# Install and build
npm ci
npm run build

# Update runtime config
echo "window.__ENV__ = { API_URL: 'https://dev.podcaststudiohub.me/api' };" > public/config.js

# Restart frontend
pm2 delete podcaststudiohub-frontend 2>/dev/null || true
PORT=3003 \
NEXT_PUBLIC_API_URL='https://dev.podcaststudiohub.me/api' \
NEXTAUTH_SECRET='<your-secret>' \
NEXTAUTH_URL='https://dev.podcaststudiohub.me' \
pm2 start npm --name podcaststudiohub-frontend --cwd /opt/podcaststudiohub/frontend -- start
pm2 save
EOF
```

#### Step 4: Restart Celery

```bash
ssh root@47.88.89.175 << 'EOF'
cd /opt/podcaststudiohub/api

pm2 delete podcaststudiohub-celery 2>/dev/null || true
pm2 start uv --name podcaststudiohub-celery --cwd /opt/podcaststudiohub/api \
  -- run celery -A src.worker:celery_app worker --loglevel=info
pm2 save
EOF
```

#### Step 5: Verify Deployment

```bash
# Check PM2 processes
ssh root@47.88.89.175 "pm2 list"

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
ssh root@47.88.89.175 "pm2 list"
```

**Check logs:**
```bash
ssh root@47.88.89.175 "pm2 logs podcaststudiohub-api --lines 50"
ssh root@47.88.89.175 "pm2 logs podcaststudiohub-frontend --lines 50"
ssh root@47.88.89.175 "pm2 logs podcaststudiohub-celery --lines 50"
```

**Restart individual service:**
```bash
ssh root@47.88.89.175 "pm2 restart podcaststudiohub-api"
ssh root@47.88.89.175 "pm2 restart podcaststudiohub-frontend"
ssh root@47.88.89.175 "pm2 restart podcaststudiohub-celery"
```

**Restart all:**
```bash
ssh root@47.88.89.175 "pm2 restart all"
```

## Environment Variables

### GitHub Secrets/Variables

Configure in **Settings** → **Environments** → **development**:

**Variables:**
- `SERVER_HOST`: `47.88.89.175`
- `SERVER_PATH`: `/opt/podcaststudiohub`
- `API_URL`: `https://dev.podcaststudiohub.me/api`
- `FRONTEND_URL`: `https://dev.podcaststudiohub.me`
- `NEXTAUTH_URL`: `https://dev.podcaststudiohub.me`
- `API_PORT`: `8001`
- `FRONTEND_PORT`: `3003`

**Secrets:**
- `SSH_PRIVATE_KEY`: SSH key for deployment
- `SERVER_USER`: `podcastfy` (the dedicated non-root service account created by
  `harden-host.sh` — see **Host Hardening** above; do **not** deploy as root)
- `NEXTAUTH_SECRET`: Generated with `openssl rand -base64 32`

### Server Environment Files

**API (`/opt/podcaststudiohub/api/.env`):**
```bash
DATABASE_URL=postgresql://user:pass@localhost/podcastfy
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
PORT=3003
```

### AWS S3 / IAM permissions

The API stores generated audio in S3 (`AWS_S3_BUCKET`, default `podcaststudiohub-audio`) using a
dedicated IAM user (e.g. `fastapi-s3-uploader`). That user needs an identity-based policy granting
**object-level** access only — the app never lists the bucket:

| Action | Why |
|---|---|
| `s3:PutObject` | upload generated audio (incl. multipart for large/long-form files) |
| `s3:GetObject` | download / `head_object` / presigned playback URLs |
| `s3:DeleteObject` | remove audio when an episode is deleted |
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

## Nginx Configuration

Nginx reverse proxy configuration is in `deployment/nginx/podcastfy.conf`.

**Routes:**
- `https://dev.podcaststudiohub.me/api` → `localhost:8001` (API)
- `https://dev.podcaststudiohub.me` → `localhost:3003` (Frontend)

The config terminates TLS 1.2/1.3 only and sends every request through a
301 HTTP→HTTPS redirect, plus HSTS / CSP / X-Frame-Options /
X-Content-Type-Options / Referrer-Policy. Port 80 never reaches the app.

## SSL / TLS (Let's Encrypt)

Certificates are obtained and renewed with `deployment/scripts/provision-ssl.sh`.
Run it once on the VPS (idempotent — safe to re-run):

```bash
# Prerequisites: DNS for the domain points at the server, port 80 open.
scp -r deployment root@47.88.89.175:/opt/podcaststudiohub/deployment
ssh root@47.88.89.175
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
scp deployment/nginx/podcastfy.conf root@47.88.89.175:/etc/nginx/sites-available/podcastfy
ssh root@47.88.89.175 "nginx -t && systemctl reload nginx"
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
ssh root@47.88.89.175

# Check PM2 status
pm2 list
pm2 logs podcaststudiohub-api --lines 100

# Try restarting
pm2 restart podcaststudiohub-api
pm2 save
```

### Database Migration Issues

```bash
ssh root@47.88.89.175 << 'EOF'
cd /opt/podcaststudiohub/api
uv run alembic current
uv run alembic history
uv run alembic upgrade head
EOF
```

### Clear All and Restart

```bash
ssh root@47.88.89.175 << 'EOF'
cd /opt/podcaststudiohub/api
pm2 delete all
pm2 save --force

# Restart API
pm2 start uv --name podcaststudiohub-api --cwd /opt/podcaststudiohub/api \
  -- run uvicorn src.main:app --host 127.0.0.1 --port 8001

# Restart Frontend
cd /opt/podcaststudiohub/frontend
PORT=3003 pm2 start npm --name podcaststudiohub-frontend --cwd /opt/podcaststudiohub/frontend -- start

# Restart Celery
cd /opt/podcaststudiohub/api
pm2 start uv --name podcaststudiohub-celery --cwd /opt/podcaststudiohub/api \
  -- run celery -A src.worker:celery_app worker --loglevel=info

pm2 save
pm2 list
EOF
```

## GitHub Actions Workflow Details

See `.github/workflows/deploy-dev.yml` for the complete workflow.

See `.github/DEPLOYMENT_SETUP.md` for GitHub configuration instructions.

---

**Server**: 47.88.89.175
**Path**: `/opt/podcaststudiohub/`
**Process Manager**: PM2
**Domain**: https://dev.podcaststudiohub.me
