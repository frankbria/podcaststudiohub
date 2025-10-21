# Podcastfy Studio - Server Deployment Quick Start

## Server: 47.88.89.175

This guide provides step-by-step instructions for deploying Podcastfy Studio on the production server.

## Prerequisites

- SSH access to root@47.88.89.175
- All deployment files in the `deployment/` directory
- Domain name (to be configured later)

## Step 1: Transfer Deployment Files

From your local machine:

```bash
# Create deployment package
cd /home/frankbria/projects/podcastfy
tar -czf podcastfy-deployment.tar.gz deployment/

# Transfer to server
scp podcastfy-deployment.tar.gz root@47.88.89.175:/tmp/

# SSH to server
ssh root@47.88.89.175

# Extract deployment files
cd /tmp
tar -xzf podcastfy-deployment.tar.gz
```

## Step 2: Run Initial Server Setup

This installs all system dependencies and creates the directory structure:

```bash
# Make setup script executable
chmod +x /tmp/deployment/scripts/setup-server.sh

# Run setup (requires root)
/tmp/deployment/scripts/setup-server.sh
```

The script will:
- ✅ Create `/var/www/podcastfy/` directory structure
- ✅ Install Python 3.11, Node.js 20, PostgreSQL 15, Redis, Nginx
- ✅ Create PostgreSQL database `podcastfy` and user `podcastfy_user`
- ✅ Configure Redis with memory limits
- ✅ Create environment file templates
- ✅ Copy Nginx configuration to `/etc/nginx/sites-available/podcastfy`

**IMPORTANT:** After this step, you MUST change the default PostgreSQL password in `/var/www/podcastfy/api/.env.template`

## Step 3: Install Systemd Services

```bash
# Copy service files
cp /tmp/deployment/systemd/*.service /etc/systemd/system/

# Reload systemd to recognize new services
systemctl daemon-reload

# Enable services to start on boot
systemctl enable podcastfy-api
systemctl enable podcastfy-celery
systemctl enable podcastfy-frontend
```

## Step 4: Configure Environment Variables

### API Environment (.env)

```bash
# Edit template with your values
nano /var/www/podcastfy/api/.env.template
```

**Required changes:**
```bash
# Change PostgreSQL password (CRITICAL!)
DATABASE_URL=postgresql://podcastfy_user:YOUR_STRONG_PASSWORD@localhost/podcastfy

# Generate encryption keys
ENCRYPTION_KEY=<run: openssl rand -hex 32>
JWT_SECRET_KEY=<run: openssl rand -hex 32>
```

**Optional (users can provide their own):**
```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
```

**Copy to production:**
```bash
cp /var/www/podcastfy/api/.env.template /var/www/podcastfy/api/.env
chmod 600 /var/www/podcastfy/api/.env
chown www-data:www-data /var/www/podcastfy/api/.env
```

### Frontend Environment (.env.local)

**Wait until domain is configured** before setting these values.

Template location: `/var/www/podcastfy/frontend/.env.local.template`

```bash
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<run: openssl rand -hex 32>
```

## Step 5: Deploy Application Code

From your local machine:

```bash
# Make deploy script executable
chmod +x deployment/scripts/deploy.sh

# Run deployment
./deployment/scripts/deploy.sh
```

The script will:
- ✅ Build Next.js frontend locally
- ✅ Deploy frontend via rsync to `/var/www/podcastfy/frontend/`
- ✅ Deploy API via rsync to `/var/www/podcastfy/api/`
- ✅ Install Python dependencies in virtual environment
- ✅ Install Node.js dependencies
- ✅ Run database migrations (Alembic)
- ✅ Restart all services
- ✅ Check service status

## Step 6: Update PostgreSQL Password

```bash
# SSH to server
ssh root@47.88.89.175

# Change PostgreSQL password to match .env file
sudo -u postgres psql -c "ALTER USER podcastfy_user WITH PASSWORD 'YOUR_STRONG_PASSWORD';"
```

## Step 7: Test Basic Setup

```bash
# Check service status
systemctl status podcastfy-api
systemctl status podcastfy-celery
systemctl status podcastfy-frontend
systemctl status nginx

# Check API health
curl http://localhost:8000/health

# Check frontend
curl http://localhost:3000

# View logs if needed
journalctl -u podcastfy-api -n 50
journalctl -u podcastfy-celery -n 50
journalctl -u podcastfy-frontend -n 50
```

## Step 8: Configure Domain (When Ready)

Once you have the domain name:

### Update Nginx Configuration

```bash
# Edit Nginx config
nano /etc/nginx/sites-available/podcastfy

# Replace all instances of:
# - "YOUR_DOMAIN" with actual domain (e.g., "studio.podcastfy.ai")
# - "_" in server_name with actual domain

# Test configuration
nginx -t

# Reload Nginx
systemctl reload nginx
```

### Configure SSL with Let's Encrypt

```bash
# Install SSL certificate
certbot --nginx -d YOUR_DOMAIN

# Follow prompts:
# 1. Enter email address
# 2. Agree to terms
# 3. Choose redirect option (recommended)

# Certbot will automatically:
# - Obtain certificate
# - Update Nginx configuration
# - Set up auto-renewal
```

### Update Frontend Environment

```bash
# Edit frontend environment
nano /var/www/podcastfy/frontend/.env.local

# Set correct URLs:
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<generate with: openssl rand -hex 32>

# Restart frontend
systemctl restart podcastfy-frontend
```

## Step 9: Configure Firewall

```bash
# Enable UFW
ufw enable

# Allow SSH (CRITICAL - do this first!)
ufw allow 22/tcp

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Check status
ufw status
```

## Step 10: Verify Deployment

```bash
# Check all services are running
systemctl status podcastfy-api podcastfy-celery podcastfy-frontend nginx

# Test API endpoint
curl https://YOUR_DOMAIN/api/health

# Test frontend
curl https://YOUR_DOMAIN

# Check logs for errors
journalctl -u podcastfy-api -n 100 --no-pager
journalctl -u podcastfy-celery -n 100 --no-pager
journalctl -u podcastfy-frontend -n 100 --no-pager
```

## Common Issues and Solutions

### API won't start
```bash
# Check logs
journalctl -u podcastfy-api -n 50

# Common causes:
# 1. Database connection failed - check DATABASE_URL in .env
# 2. Missing dependencies - reinstall:
cd /var/www/podcastfy/api
source .venv/bin/activate
pip install -r requirements.txt
deactivate

# 3. Port conflict - check: netstat -tulpn | grep 8000
```

### Celery worker not processing
```bash
# Check logs
journalctl -u podcastfy-celery -n 50

# Test Redis connection
redis-cli ping

# Should return: PONG

# Restart worker
systemctl restart podcastfy-celery
```

### Frontend not loading
```bash
# Check logs
journalctl -u podcastfy-frontend -n 50

# Check if running
netstat -tulpn | grep 3000

# Rebuild if needed
cd /var/www/podcastfy/frontend
npm run build
systemctl restart podcastfy-frontend
```

### Nginx errors
```bash
# Test configuration
nginx -t

# Check error logs
tail -f /var/www/podcastfy/logs/frontend-error.log

# Common issues:
# 1. SSL certificate - renew: certbot renew
# 2. Upstream not responding - check API is running
# 3. Permission denied - check file ownership
```

## Security Checklist

Before going live:

- [ ] Changed default PostgreSQL password
- [ ] Generated strong ENCRYPTION_KEY and JWT_SECRET_KEY
- [ ] Configured firewall (ufw) - SSH, HTTP, HTTPS only
- [ ] Set up SSL with Let's Encrypt
- [ ] Configured automatic security updates
- [ ] Set up fail2ban for SSH protection (optional but recommended)
- [ ] Configured database backups
- [ ] Reviewed logs for suspicious activity
- [ ] Set proper file permissions (www-data:www-data)

## Backup Strategy

### Database Backup

```bash
# Create backup script
cat > /usr/local/bin/backup-podcastfy-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/podcastfy"
mkdir -p $BACKUP_DIR
sudo -u postgres pg_dump podcastfy | gzip > $BACKUP_DIR/podcastfy-$(date +%Y%m%d-%H%M%S).sql.gz
# Keep only last 7 days
find $BACKUP_DIR -name "podcastfy-*.sql.gz" -mtime +7 -delete
EOF

chmod +x /usr/local/bin/backup-podcastfy-db.sh

# Add to crontab (daily at 2 AM)
echo "0 2 * * * /usr/local/bin/backup-podcastfy-db.sh" | crontab -
```

### File Backup

```bash
# Backup uploads and audio files
tar -czf /var/backups/podcastfy-files-$(date +%Y%m%d).tar.gz \
    /var/www/podcastfy/uploads/ \
    /var/www/podcastfy/data/audio/
```

## Monitoring

### Set Up Basic Monitoring

```bash
# Install monitoring tools
apt-get install -y htop iotop nethogs

# Check system resources
htop                           # CPU and memory
df -h                          # Disk usage
du -sh /var/www/podcastfy/*   # Application size

# Check service health
systemctl status podcastfy-api podcastfy-celery podcastfy-frontend nginx
```

### Log Monitoring

```bash
# Real-time log monitoring
journalctl -u podcastfy-api -f           # API logs
journalctl -u podcastfy-celery -f        # Celery logs
journalctl -u podcastfy-frontend -f      # Frontend logs
tail -f /var/www/podcastfy/logs/frontend-access.log  # Nginx access
tail -f /var/www/podcastfy/logs/frontend-error.log   # Nginx errors
```

## Maintenance Commands

### Update Application

```bash
# Pull latest code
cd /home/frankbria/projects/podcastfy
git pull origin main

# Run deployment
./deployment/scripts/deploy.sh
```

### Restart Services

```bash
# Restart all
systemctl restart podcastfy-api podcastfy-celery podcastfy-frontend
systemctl reload nginx

# Restart individual
systemctl restart podcastfy-api
systemctl restart podcastfy-celery
systemctl restart podcastfy-frontend
```

### Clean Up Logs

```bash
# Rotate logs manually
logrotate -f /etc/logrotate.d/nginx

# Clean journal logs older than 7 days
journalctl --vacuum-time=7d
```

## Support and Troubleshooting

For detailed troubleshooting, see: `deployment/DEPLOYMENT.md`

Common commands:
```bash
# Service status
systemctl status SERVICE_NAME

# Service logs (last 50 lines)
journalctl -u SERVICE_NAME -n 50

# Service logs (follow)
journalctl -u SERVICE_NAME -f

# Check listening ports
netstat -tulpn

# Check database connection
sudo -u postgres psql -d podcastfy -c "SELECT version();"

# Check Redis connection
redis-cli ping
```

## Next Steps After Deployment

1. **Create first admin user** via API or Django admin
2. **Test podcast generation workflow** from UI
3. **Set up monitoring alerts** (optional)
4. **Configure backup automation**
5. **Document any custom configurations**

## Application URLs (After Domain Configuration)

- **Frontend**: https://YOUR_DOMAIN
- **API**: https://YOUR_DOMAIN/api
- **API Documentation**: https://YOUR_DOMAIN/api/docs
- **API Health Check**: https://YOUR_DOMAIN/api/health

## Files Created During Setup

```
/var/www/podcastfy/
├── api/
│   ├── .venv/              # Python virtual environment
│   ├── .env                # API environment variables (YOU MUST CONFIGURE)
│   └── src/                # API source code (deployed by script)
├── frontend/
│   ├── .next/              # Built Next.js application
│   ├── .env.local          # Frontend environment (CONFIGURE AFTER DOMAIN)
│   └── ...                 # Frontend source code (deployed by script)
├── logs/
│   ├── frontend-access.log
│   └── frontend-error.log
├── ssl/                    # SSL certificates (created by certbot)
└── uploads/                # User uploaded files

/etc/nginx/sites-available/podcastfy    # Nginx configuration
/etc/systemd/system/podcastfy-*.service # Systemd services
```

## Environment File Templates

### API (.env) - MUST BE CONFIGURED BEFORE DEPLOYMENT

Location: `/var/www/podcastfy/api/.env`

```bash
# Database (CHANGE PASSWORD!)
DATABASE_URL=postgresql://podcastfy_user:CHANGE_THIS_PASSWORD@localhost/podcastfy

# Redis
REDIS_URL=redis://localhost:6379/0

# Security (GENERATE THESE!)
ENCRYPTION_KEY=<openssl rand -hex 32>
JWT_SECRET_KEY=<openssl rand -hex 32>
JWT_ALGORITHM=RS256

# Optional API Keys
OPENAI_API_KEY=
GEMINI_API_KEY=
ELEVENLABS_API_KEY=

# Application
DEBUG=False
LOG_LEVEL=INFO
```

### Frontend (.env.local) - CONFIGURE AFTER DOMAIN SETUP

Location: `/var/www/podcastfy/frontend/.env.local`

```bash
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<openssl rand -hex 32>
```

## Deployment Checklist

Pre-deployment:
- [ ] All deployment files transferred to server
- [ ] Server setup script executed successfully
- [ ] PostgreSQL password changed from default
- [ ] API `.env` file configured with generated keys
- [ ] Systemd services installed and enabled

Deployment:
- [ ] Application code deployed via `deploy.sh`
- [ ] Database migrations completed
- [ ] All services started successfully
- [ ] Health check endpoints responding

Post-deployment (with domain):
- [ ] Domain DNS configured
- [ ] Nginx configuration updated with domain
- [ ] SSL certificate installed via certbot
- [ ] Frontend `.env.local` configured
- [ ] Firewall configured
- [ ] Backup automation configured

Testing:
- [ ] Frontend loads at https://YOUR_DOMAIN
- [ ] API docs accessible at https://YOUR_DOMAIN/api/docs
- [ ] User registration works
- [ ] Project creation works
- [ ] Episode creation works
- [ ] Podcast generation works
- [ ] Audio playback works

---

**For detailed documentation, see:**
- `deployment/DEPLOYMENT.md` - Comprehensive deployment guide
- `deployment/nginx/podcastfy.conf` - Nginx configuration reference
- `deployment/systemd/*.service` - Systemd service configurations
