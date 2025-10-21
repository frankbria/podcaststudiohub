# Podcastfy Studio - Deployment Configuration

This directory contains all configuration files and scripts needed to deploy Podcastfy Studio to production.

## Server Information

- **IP Address**: 47.88.89.175
- **Target Directory**: `/var/www/podcastfy/`
- **OS**: Ubuntu/Debian
- **Web Server**: Nginx
- **Domain**: *To be configured*

## Directory Structure

```
deployment/
├── README.md                    # This file
├── QUICKSTART.md               # Step-by-step deployment guide (START HERE!)
├── DEPLOYMENT.md               # Comprehensive deployment documentation
├── nginx/
│   └── podcastfy.conf          # Nginx reverse proxy configuration
├── systemd/
│   ├── podcastfy-api.service   # FastAPI/Uvicorn service
│   ├── podcastfy-celery.service # Celery worker service
│   └── podcastfy-frontend.service # Next.js production service
└── scripts/
    ├── setup-server.sh         # Initial server setup script
    └── deploy.sh               # Automated deployment script
```

## Quick Start

**New deployment? Start here:**

1. Read `QUICKSTART.md` for step-by-step instructions
2. Transfer files to server: `scp -r deployment/ root@47.88.89.175:/tmp/`
3. SSH to server: `ssh root@47.88.89.175`
4. Run setup: `/tmp/deployment/scripts/setup-server.sh`
5. Configure environment variables
6. Run deployment: `./deployment/scripts/deploy.sh`

## File Descriptions

### Configuration Files

**`nginx/podcastfy.conf`**
- Nginx reverse proxy configuration
- Routes `/api/*` to FastAPI backend (port 8000)
- Routes `/*` to Next.js frontend (port 3000)
- SSL ready (commented out, uncomment after certbot)
- SSE support for real-time progress updates
- Long timeouts (600s) for podcast generation
- 50MB file upload limit

**`systemd/podcastfy-api.service`**
- FastAPI application service
- Runs with Uvicorn (4 workers)
- User: www-data
- Working directory: `/var/www/podcastfy/api`
- Environment: `.env` file
- Auto-restart on failure

**`systemd/podcastfy-celery.service`**
- Celery worker service
- Concurrency: 2 workers
- Max tasks per child: 10
- Time limit: 900s (15 min)
- Soft time limit: 600s (10 min)
- Auto-restart on failure

**`systemd/podcastfy-frontend.service`**
- Next.js production server
- Port: 3000
- Environment: `.env.local` file
- User: www-data
- Auto-restart on failure

### Scripts

**`scripts/setup-server.sh`**
- **Purpose**: Initial server infrastructure setup
- **Run once**: On first deployment only
- **Actions**:
  - Creates `/var/www/podcastfy/` directory structure
  - Installs system dependencies (Python 3.11, Node.js 20, PostgreSQL, Redis, Nginx)
  - Creates PostgreSQL database and user
  - Configures Redis with memory limits
  - Copies Nginx configuration
  - Creates environment file templates

**`scripts/deploy.sh`**
- **Purpose**: Deploy application code and restart services
- **Run**: Every time you want to deploy updates
- **Actions**:
  - Builds Next.js frontend locally
  - Deploys frontend and API via rsync
  - Installs Python dependencies in virtual environment
  - Installs Node.js dependencies
  - Runs database migrations (Alembic)
  - Restarts all services (API, Celery, Frontend)
  - Checks service status

### Documentation

**`QUICKSTART.md`**
- Step-by-step deployment guide
- Start here if this is your first deployment
- Includes troubleshooting and checklists

**`DEPLOYMENT.md`**
- Comprehensive deployment documentation
- Service management commands
- Monitoring and troubleshooting
- Security configuration
- Backup procedures
- Performance tuning

## Deployment Workflow

### First-Time Deployment

```bash
# 1. Transfer deployment files
cd /home/frankbria/projects/podcastfy
tar -czf podcastfy-deployment.tar.gz deployment/
scp podcastfy-deployment.tar.gz root@47.88.89.175:/tmp/

# 2. SSH to server
ssh root@47.88.89.175

# 3. Extract and run setup
cd /tmp
tar -xzf podcastfy-deployment.tar.gz
chmod +x deployment/scripts/setup-server.sh
./deployment/scripts/setup-server.sh

# 4. Install systemd services
cp deployment/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable podcastfy-api podcastfy-celery podcastfy-frontend

# 5. Configure environment variables
nano /var/www/podcastfy/api/.env.template
# Edit: DATABASE_URL password, ENCRYPTION_KEY, JWT_SECRET_KEY

cp /var/www/podcastfy/api/.env.template /var/www/podcastfy/api/.env
chmod 600 /var/www/podcastfy/api/.env
chown www-data:www-data /var/www/podcastfy/api/.env

# 6. Update PostgreSQL password
sudo -u postgres psql -c "ALTER USER podcastfy_user WITH PASSWORD 'YOUR_PASSWORD';"

# 7. Return to local machine and deploy
exit
./deployment/scripts/deploy.sh
```

### Subsequent Deployments

```bash
# From local machine
cd /home/frankbria/projects/podcastfy
git pull origin main
./deployment/scripts/deploy.sh
```

### Domain Configuration (When Ready)

```bash
# 1. SSH to server
ssh root@47.88.89.175

# 2. Update Nginx configuration
nano /etc/nginx/sites-available/podcastfy
# Replace: YOUR_DOMAIN with actual domain
# Replace: _ in server_name with actual domain

# 3. Test and reload Nginx
nginx -t
systemctl reload nginx

# 4. Install SSL certificate
certbot --nginx -d YOUR_DOMAIN

# 5. Update frontend environment
nano /var/www/podcastfy/frontend/.env.local
# Set: NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
# Set: NEXTAUTH_URL=https://YOUR_DOMAIN
# Set: NEXTAUTH_SECRET=<openssl rand -hex 32>

cp /var/www/podcastfy/frontend/.env.local.template /var/www/podcastfy/frontend/.env.local

# 6. Restart frontend
systemctl restart podcastfy-frontend
```

## Environment Variables

### API Environment (`/var/www/podcastfy/api/.env`)

**Required:**
```bash
DATABASE_URL=postgresql://podcastfy_user:PASSWORD@localhost/podcastfy
REDIS_URL=redis://localhost:6379/0
ENCRYPTION_KEY=<openssl rand -hex 32>
JWT_SECRET_KEY=<openssl rand -hex 32>
JWT_ALGORITHM=RS256
DEBUG=False
LOG_LEVEL=INFO
```

**Optional (users can provide their own):**
```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=...
```

### Frontend Environment (`/var/www/podcastfy/frontend/.env.local`)

**Configure after domain is set up:**
```bash
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<openssl rand -hex 32>
```

## Service Management

### Start/Stop/Restart

```bash
# All services
systemctl restart podcastfy-api podcastfy-celery podcastfy-frontend

# Individual services
systemctl start podcastfy-api
systemctl stop podcastfy-api
systemctl restart podcastfy-api
systemctl status podcastfy-api

# View logs
journalctl -u podcastfy-api -f
journalctl -u podcastfy-celery -f
journalctl -u podcastfy-frontend -f
```

### Check Status

```bash
# All services at once
systemctl status podcastfy-api podcastfy-celery podcastfy-frontend nginx

# Check listening ports
netstat -tulpn | grep -E '(3000|8000)'

# Test API health
curl http://localhost:8000/health

# Test frontend
curl http://localhost:3000
```

## Directory Structure on Server

After deployment, the server will have:

```
/var/www/podcastfy/
├── api/                       # FastAPI application
│   ├── .venv/                 # Python virtual environment
│   ├── .env                   # API environment variables
│   ├── src/                   # Source code
│   ├── alembic/              # Database migrations
│   └── requirements.txt       # Python dependencies
├── frontend/                  # Next.js application
│   ├── .next/                 # Built Next.js files
│   ├── .env.local            # Frontend environment variables
│   ├── node_modules/          # Node dependencies
│   └── ...                    # Frontend source
├── logs/                      # Application logs
│   ├── frontend-access.log
│   └── frontend-error.log
├── ssl/                       # SSL certificates (Let's Encrypt)
├── uploads/                   # User uploaded files
└── data/
    └── audio/                 # Generated podcast files

/etc/nginx/sites-available/podcastfy    # Nginx config
/etc/systemd/system/
├── podcastfy-api.service
├── podcastfy-celery.service
└── podcastfy-frontend.service
```

## Security Checklist

Before going live:

- [ ] Change default PostgreSQL password
- [ ] Generate strong ENCRYPTION_KEY and JWT_SECRET_KEY
- [ ] Configure firewall (allow only SSH, HTTP, HTTPS)
- [ ] Set up SSL with Let's Encrypt
- [ ] Set proper file permissions (www-data:www-data)
- [ ] Configure automatic security updates
- [ ] Set up database backups
- [ ] Review Nginx security headers
- [ ] Enable fail2ban for SSH protection (recommended)

## Firewall Configuration

```bash
# Enable firewall
ufw enable

# Allow SSH (CRITICAL - do this first!)
ufw allow 22/tcp

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Check status
ufw status
```

## Troubleshooting

### API won't start
```bash
journalctl -u podcastfy-api -n 50
# Check: DATABASE_URL, missing dependencies, port conflicts
```

### Celery not processing
```bash
journalctl -u podcastfy-celery -n 50
redis-cli ping  # Should return PONG
```

### Frontend not loading
```bash
journalctl -u podcastfy-frontend -n 50
netstat -tulpn | grep 3000
cd /var/www/podcastfy/frontend && npm run build
```

### Nginx errors
```bash
nginx -t
tail -f /var/www/podcastfy/logs/frontend-error.log
```

See `DEPLOYMENT.md` for detailed troubleshooting.

## Monitoring

### System Resources
```bash
htop                           # CPU and memory
df -h                          # Disk usage
du -sh /var/www/podcastfy/*   # Application size
```

### Service Health
```bash
systemctl status podcastfy-api podcastfy-celery podcastfy-frontend nginx
curl http://localhost:8000/health
```

### Logs
```bash
# Real-time monitoring
journalctl -u podcastfy-api -f
journalctl -u podcastfy-celery -f
journalctl -u podcastfy-frontend -f
tail -f /var/www/podcastfy/logs/frontend-access.log
```

## Backup

### Database Backup
```bash
# Manual backup
sudo -u postgres pg_dump podcastfy | gzip > /var/backups/podcastfy-$(date +%Y%m%d).sql.gz

# Automated daily backup (add to crontab)
0 2 * * * sudo -u postgres pg_dump podcastfy | gzip > /var/backups/podcastfy-$(date +\%Y\%m\%d).sql.gz
```

### File Backup
```bash
tar -czf /var/backups/podcastfy-files-$(date +%Y%m%d).tar.gz \
    /var/www/podcastfy/uploads/ \
    /var/www/podcastfy/data/audio/
```

## Performance Tuning

See `DEPLOYMENT.md` for detailed performance tuning (Nginx workers, PostgreSQL buffers, Redis memory).

## Support

- **QUICKSTART.md**: Step-by-step deployment guide
- **DEPLOYMENT.md**: Comprehensive documentation
- **GitHub Issues**: https://github.com/souzatharsis/podcastfy/issues

## Files in This Directory

| File | Purpose | When to Use |
|------|---------|-------------|
| `QUICKSTART.md` | Step-by-step guide | First deployment |
| `DEPLOYMENT.md` | Comprehensive docs | Reference, troubleshooting |
| `nginx/podcastfy.conf` | Nginx config | Copy to `/etc/nginx/sites-available/` |
| `systemd/*.service` | Service definitions | Copy to `/etc/systemd/system/` |
| `scripts/setup-server.sh` | Initial setup | Run once on new server |
| `scripts/deploy.sh` | Deploy updates | Run every deployment |

## Next Steps

1. **Read `QUICKSTART.md`** for detailed step-by-step instructions
2. **Run setup script** to prepare server infrastructure
3. **Configure environment variables** (API keys, database password)
4. **Deploy application** using deploy.sh script
5. **Configure domain** when ready
6. **Set up SSL** with Let's Encrypt
7. **Test everything** works end-to-end

---

**Server**: 47.88.89.175
**Target**: `/var/www/podcastfy/`
**Domain**: *To be configured*
