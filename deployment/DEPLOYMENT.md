# Podcastfy Studio - Deployment Guide

## Server Information

- **IP Address**: 47.88.89.175
- **OS**: Ubuntu/Debian (assumed)
- **Application Directory**: `/var/www/podcastfy/`
- **Web Server**: Nginx
- **Domain**: *To be configured*

## Directory Structure

```
/var/www/podcastfy/
├── frontend/           # Next.js application
│   ├── .next/         # Built Next.js files
│   ├── node_modules/  # Node dependencies
│   ├── .env.local     # Frontend environment variables
│   └── ...
├── api/               # FastAPI application
│   ├── .venv/         # Python virtual environment
│   ├── src/           # Source code
│   ├── alembic/       # Database migrations
│   ├── .env           # API environment variables
│   └── ...
├── logs/              # Application logs
│   ├── frontend-access.log
│   ├── frontend-error.log
│   └── ...
├── ssl/               # SSL certificates (Let's Encrypt)
│   ├── fullchain.pem
│   └── privkey.pem
└── uploads/           # User uploaded files
```

## Initial Server Setup

### 1. Run Server Setup Script

Copy the setup script to the server and execute:

```bash
# On your local machine
scp deployment/scripts/setup-server.sh root@47.88.89.175:/tmp/
scp deployment/nginx/podcastfy.conf root@47.88.89.175:/tmp/

# SSH to server
ssh root@47.88.89.175

# Run setup
chmod +x /tmp/setup-server.sh
/tmp/setup-server.sh
```

This script will:
- Create application directories
- Install system dependencies (Python, Node.js, PostgreSQL, Redis, Nginx, etc.)
- Configure PostgreSQL database
- Configure Redis
- Set up Nginx
- Create environment file templates

### 2. Configure Environment Variables

#### API Environment (.env)

```bash
# Edit the template
nano /var/www/podcastfy/api/.env.template

# Copy to .env
cp /var/www/podcastfy/api/.env.template /var/www/podcastfy/api/.env
chmod 600 /var/www/podcastfy/api/.env
chown www-data:www-data /var/www/podcastfy/api/.env
```

Required variables:
```bash
DATABASE_URL=postgresql://podcastfy_user:YOUR_PASSWORD@localhost/podcastfy
REDIS_URL=redis://localhost:6379/0
ENCRYPTION_KEY=<generate with: openssl rand -hex 32>
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
JWT_ALGORITHM=RS256
DEBUG=False
LOG_LEVEL=INFO
```

Optional API keys (users can provide their own):
```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
```

#### Frontend Environment (.env.local)

```bash
# Edit the template
nano /var/www/podcastfy/frontend/.env.local.template

# Copy to .env.local
cp /var/www/podcastfy/frontend/.env.local.template /var/www/podcastfy/frontend/.env.local
```

Required variables (update after domain is configured):
```bash
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<generate with: openssl rand -hex 32>
```

### 3. Install Systemd Services

```bash
# Copy service files
cp deployment/systemd/*.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable services
systemctl enable podcastfy-api
systemctl enable podcastfy-celery
systemctl enable podcastfy-frontend
```

## Deployment Process

### Method 1: Automated Deployment Script

From your local machine:

```bash
# Make script executable
chmod +x deployment/scripts/deploy.sh

# Run deployment
./deployment/scripts/deploy.sh
```

The script will:
1. Build the frontend
2. Deploy frontend and API code via rsync
3. Install dependencies on server
4. Run database migrations
5. Restart all services

### Method 2: Manual Deployment

#### Deploy Frontend

```bash
# Build locally
cd apps/web
npm install
npm run build

# Deploy to server
rsync -avz --delete \
    --exclude 'node_modules' \
    --exclude '.next/cache' \
    . root@47.88.89.175:/var/www/podcastfy/frontend/

# On server: Install dependencies
ssh root@47.88.89.175
cd /var/www/podcastfy/frontend
npm ci --production
systemctl restart podcastfy-frontend
```

#### Deploy API

```bash
# Deploy code
rsync -avz --delete \
    --exclude '.venv' \
    --exclude '__pycache__' \
    apps/api/ root@47.88.89.175:/var/www/podcastfy/api/

# On server: Install dependencies and migrate
ssh root@47.88.89.175
cd /var/www/podcastfy/api
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
deactivate

# Restart services
systemctl restart podcastfy-api
systemctl restart podcastfy-celery
```

## Domain Configuration

### 1. Update Nginx Configuration

Once you have the domain name:

```bash
# On server
nano /etc/nginx/sites-available/podcastfy

# Replace all instances of:
# - "YOUR_DOMAIN" with actual domain (e.g., "podcastfy.example.com")
# - "_" in server_name with actual domain

# Test configuration
nginx -t

# Reload Nginx
systemctl reload nginx
```

### 2. Configure SSL with Let's Encrypt

```bash
# Install SSL certificate
certbot --nginx -d YOUR_DOMAIN

# Follow prompts to:
# 1. Enter email address
# 2. Agree to terms
# 3. Choose redirect option (recommended)

# Certbot will automatically:
# - Obtain certificate
# - Update Nginx configuration
# - Set up auto-renewal
```

### 3. Update Environment Variables

```bash
# Update API URL in frontend
nano /var/www/podcastfy/frontend/.env.local
# Change: NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
# Change: NEXTAUTH_URL=https://YOUR_DOMAIN

# Restart frontend
systemctl restart podcastfy-frontend
```

## Service Management

### Start/Stop/Restart Services

```bash
# API
systemctl start podcastfy-api
systemctl stop podcastfy-api
systemctl restart podcastfy-api
systemctl status podcastfy-api

# Celery Worker
systemctl start podcastfy-celery
systemctl stop podcastfy-celery
systemctl restart podcastfy-celery
systemctl status podcastfy-celery

# Frontend
systemctl start podcastfy-frontend
systemctl stop podcastfy-frontend
systemctl restart podcastfy-frontend
systemctl status podcastfy-frontend

# Nginx
systemctl reload nginx
systemctl restart nginx
systemctl status nginx
```

### View Logs

```bash
# API logs
journalctl -u podcastfy-api -f

# Celery logs
journalctl -u podcastfy-celery -f

# Frontend logs
journalctl -u podcastfy-frontend -f

# Nginx access logs
tail -f /var/www/podcastfy/logs/frontend-access.log

# Nginx error logs
tail -f /var/www/podcastfy/logs/frontend-error.log
```

## Database Management

### Create Backup

```bash
# Create backup
sudo -u postgres pg_dump podcastfy > /var/backups/podcastfy-$(date +%Y%m%d).sql

# Compress backup
gzip /var/backups/podcastfy-$(date +%Y%m%d).sql
```

### Restore Backup

```bash
# Restore from backup
gunzip /var/backups/podcastfy-20241020.sql.gz
sudo -u postgres psql podcastfy < /var/backups/podcastfy-20241020.sql
```

### Run Migrations

```bash
cd /var/www/podcastfy/api
source .venv/bin/activate
alembic upgrade head
deactivate
```

## Monitoring

### Check System Resources

```bash
# CPU and memory
htop

# Disk usage
df -h

# Application directory size
du -sh /var/www/podcastfy/*
```

### Check Service Health

```bash
# API health endpoint
curl http://localhost:8000/health

# Check all services
systemctl status podcastfy-api podcastfy-celery podcastfy-frontend nginx
```

## Troubleshooting

### API not starting

```bash
# Check logs
journalctl -u podcastfy-api -n 50

# Common issues:
# 1. Database connection - check DATABASE_URL in .env
# 2. Missing dependencies - reinstall: pip install -r requirements.txt
# 3. Port conflict - check: netstat -tulpn | grep 8000
```

### Celery worker not processing tasks

```bash
# Check logs
journalctl -u podcastfy-celery -n 50

# Check Redis connection
redis-cli ping

# Restart worker
systemctl restart podcastfy-celery
```

### Frontend not loading

```bash
# Check logs
journalctl -u podcastfy-frontend -n 50

# Check if running
netstat -tulpn | grep 3000

# Rebuild
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
# 1. SSL certificate issues - renew: certbot renew
# 2. Upstream not responding - check API is running
```

## Security Checklist

- [ ] Change default PostgreSQL password
- [ ] Generate strong ENCRYPTION_KEY and JWT_SECRET_KEY
- [ ] Configure firewall (ufw)
- [ ] Set up SSL with Let's Encrypt
- [ ] Enable automatic security updates
- [ ] Configure fail2ban for SSH protection
- [ ] Regular database backups
- [ ] Monitor logs for suspicious activity

## Firewall Configuration

```bash
# Enable UFW
ufw enable

# Allow SSH
ufw allow 22/tcp

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Check status
ufw status
```

## Maintenance

### Update Application

```bash
# Pull latest code
git pull origin main

# Run deployment script
./deployment/scripts/deploy.sh
```

### Update SSL Certificate

```bash
# Certificates auto-renew, but to manually renew:
certbot renew

# Test renewal
certbot renew --dry-run
```

### Clean Up Old Logs

```bash
# Rotate logs manually
logrotate -f /etc/logrotate.d/nginx

# Clean journal logs older than 7 days
journalctl --vacuum-time=7d
```

## Performance Tuning

### Nginx

```bash
# Edit nginx.conf
nano /etc/nginx/nginx.conf

# Increase worker_processes to number of CPU cores
worker_processes auto;

# Increase worker_connections
events {
    worker_connections 2048;
}
```

### PostgreSQL

```bash
# Edit postgresql.conf
nano /etc/postgresql/15/main/postgresql.conf

# Increase shared_buffers (25% of RAM)
shared_buffers = 2GB

# Increase work_mem
work_mem = 64MB

# Restart PostgreSQL
systemctl restart postgresql
```

### Redis

```bash
# Edit redis.conf
nano /etc/redis/redis.conf

# Increase maxmemory based on available RAM
maxmemory 1gb

# Restart Redis
systemctl restart redis-server
```

## Support

For issues or questions:
- Check logs first (journalctl -u SERVICE_NAME)
- Review error messages in Nginx logs
- Verify environment variables are set correctly
- Check service status: systemctl status SERVICE_NAME
