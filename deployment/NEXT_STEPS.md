# Podcastfy Studio - Deployment Next Steps

## Current Status ✅

All deployment infrastructure has been created and committed to the repository:

- ✅ Nginx reverse proxy configuration
- ✅ Systemd service definitions (API, Celery, Frontend)
- ✅ Server setup script (dependencies, PostgreSQL, Redis)
- ✅ Automated deployment script
- ✅ Comprehensive documentation (QUICKSTART.md, DEPLOYMENT.md)

**Server**: 47.88.89.175
**Target Directory**: `/var/www/podcastfy/`
**Branch**: `001-gui-podcast-studio`

## Immediate Next Steps

### 1. Transfer Deployment Files to Server

```bash
# From local machine (/home/frankbria/projects/podcastfy)
cd /home/frankbria/projects/podcastfy

# Create deployment package
tar -czf podcastfy-deployment.tar.gz deployment/

# Transfer to server
scp podcastfy-deployment.tar.gz root@47.88.89.175:/tmp/

# Verify transfer
ssh root@47.88.89.175 "ls -lh /tmp/podcastfy-deployment.tar.gz"
```

### 2. Execute Initial Server Setup

```bash
# SSH to server
ssh root@47.88.89.175

# Extract deployment files
cd /tmp
tar -xzf podcastfy-deployment.tar.gz

# Make setup script executable
chmod +x deployment/scripts/setup-server.sh

# Run initial setup (installs dependencies, creates directories)
./deployment/scripts/setup-server.sh

# This will:
# - Install Python 3.11, Node.js 20, PostgreSQL 15, Redis, Nginx
# - Create /var/www/podcastfy/ directory structure
# - Create PostgreSQL database 'podcastfy' and user 'podcastfy_user'
# - Configure Redis with memory limits
# - Copy Nginx configuration
# - Create environment file templates
```

### 3. Install Systemd Services

```bash
# Still on server
cp /tmp/deployment/systemd/*.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable services to start on boot
systemctl enable podcastfy-api
systemctl enable podcastfy-celery
systemctl enable podcastfy-frontend
```

### 4. Configure Environment Variables

**CRITICAL**: You must configure environment variables before deploying application code.

#### API Environment (.env)

```bash
# Edit the template
nano /var/www/podcastfy/api/.env.template

# Required changes:
# 1. Change PostgreSQL password (CRITICAL!)
DATABASE_URL=postgresql://podcastfy_user:YOUR_STRONG_PASSWORD@localhost/podcastfy

# 2. Generate encryption keys
ENCRYPTION_KEY=<run: openssl rand -hex 32>
JWT_SECRET_KEY=<run: openssl rand -hex 32>

# 3. Optional: Add API keys (users can provide their own later)
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...

# Copy to production
cp /var/www/podcastfy/api/.env.template /var/www/podcastfy/api/.env
chmod 600 /var/www/podcastfy/api/.env
chown www-data:www-data /var/www/podcastfy/api/.env
```

#### Update PostgreSQL Password

```bash
# Change PostgreSQL password to match .env file
sudo -u postgres psql -c "ALTER USER podcastfy_user WITH PASSWORD 'YOUR_STRONG_PASSWORD';"
```

#### Frontend Environment (.env.local)

**NOTE**: Wait until domain is configured before setting these values.

Template is at: `/var/www/podcastfy/frontend/.env.local.template`

Will need:
```bash
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<openssl rand -hex 32>
```

### 5. Deploy Application Code

```bash
# Exit server and return to local machine
exit

# From local machine (/home/frankbria/projects/podcastfy)
cd /home/frankbria/projects/podcastfy

# Make deploy script executable
chmod +x deployment/scripts/deploy.sh

# Run deployment
./deployment/scripts/deploy.sh

# This will:
# - Build Next.js frontend locally
# - Deploy frontend to /var/www/podcastfy/frontend/ via rsync
# - Deploy API to /var/www/podcastfy/api/ via rsync
# - Install Python dependencies in virtual environment
# - Install Node.js dependencies
# - Run database migrations (Alembic)
# - Restart all services
# - Check service status
```

### 6. Verify Basic Setup (Without Domain)

```bash
# SSH to server
ssh root@47.88.89.175

# Check service status
systemctl status podcastfy-api
systemctl status podcastfy-celery
systemctl status podcastfy-frontend
systemctl status nginx

# Check API health (should return JSON)
curl http://localhost:8000/health

# Check frontend (should return HTML)
curl http://localhost:3000

# View logs if needed
journalctl -u podcastfy-api -n 50
journalctl -u podcastfy-celery -n 50
journalctl -u podcastfy-frontend -n 50
```

### 7. Configure Firewall

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

## When Domain is Ready

Once you have the domain name (e.g., `studio.podcastfy.ai`):

### 1. Update Nginx Configuration

```bash
# SSH to server
ssh root@47.88.89.175

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

### 2. Configure SSL with Let's Encrypt

```bash
# Install SSL certificate
certbot --nginx -d YOUR_DOMAIN

# Follow prompts:
# 1. Enter email address
# 2. Agree to terms
# 3. Choose redirect option (recommended)

# Certbot will automatically:
# - Obtain certificate
# - Update Nginx configuration with SSL settings
# - Set up auto-renewal
```

### 3. Update Frontend Environment

```bash
# Edit frontend environment
nano /var/www/podcastfy/frontend/.env.local

# Set correct values:
NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN/api
NEXTAUTH_URL=https://YOUR_DOMAIN
NEXTAUTH_SECRET=<generate with: openssl rand -hex 32>

# Restart frontend
systemctl restart podcastfy-frontend
```

### 4. Test Production URLs

```bash
# Test API
curl https://YOUR_DOMAIN/api/health

# Test frontend (from browser)
# Open: https://YOUR_DOMAIN

# Test API docs
# Open: https://YOUR_DOMAIN/api/docs
```

## Post-Deployment Checklist

After deployment is complete:

### Security
- [ ] Changed default PostgreSQL password
- [ ] Generated strong ENCRYPTION_KEY and JWT_SECRET_KEY
- [ ] Configured firewall (SSH, HTTP, HTTPS only)
- [ ] Set up SSL with Let's Encrypt
- [ ] Verified file permissions (www-data:www-data)
- [ ] Configured automatic security updates (optional)
- [ ] Set up fail2ban for SSH protection (optional)

### Functionality
- [ ] All services running (API, Celery, Frontend, Nginx)
- [ ] API health endpoint responding
- [ ] Frontend loads in browser
- [ ] User registration works
- [ ] User login works
- [ ] Project creation works
- [ ] Episode creation works
- [ ] Content source upload works
- [ ] Podcast generation works (end-to-end test)
- [ ] Audio playback works
- [ ] Real-time progress updates work (SSE)

### Monitoring
- [ ] Set up database backups (daily recommended)
- [ ] Configured log rotation
- [ ] Verified service auto-restart on failure
- [ ] Set up monitoring alerts (optional)

### Documentation
- [ ] Documented any custom configurations
- [ ] Noted any issues encountered during deployment
- [ ] Updated team with application URLs
- [ ] Created admin user for initial testing

## Testing the MVP

Once deployed, test the complete podcast generation workflow:

1. **Register a user**
   - Go to https://YOUR_DOMAIN/signup
   - Create account with email/password

2. **Create a project**
   - Go to https://YOUR_DOMAIN/dashboard
   - Click "New Project"
   - Enter project name and description

3. **Create an episode**
   - Click on project
   - Click "New Episode"
   - Enter episode title

4. **Add content sources**
   - Click on episode
   - Add URL, file, or text content
   - Save content source

5. **Generate podcast**
   - Click "Generate Podcast"
   - Watch real-time progress bar
   - Wait for completion (may take several minutes)

6. **Play podcast**
   - Once complete, audio player appears
   - Test playback
   - Verify audio quality

## Troubleshooting

If you encounter issues during deployment, see:

- **`deployment/QUICKSTART.md`** - Common issues and solutions
- **`deployment/DEPLOYMENT.md`** - Detailed troubleshooting section

### Quick Diagnostics

```bash
# Check all services
systemctl status podcastfy-api podcastfy-celery podcastfy-frontend nginx

# Check logs
journalctl -u podcastfy-api -n 100
journalctl -u podcastfy-celery -n 100
journalctl -u podcastfy-frontend -n 100

# Check listening ports
netstat -tulpn | grep -E '(3000|8000)'

# Check database connection
sudo -u postgres psql -d podcastfy -c "SELECT version();"

# Check Redis connection
redis-cli ping
```

## Maintenance

### Regular Updates

```bash
# From local machine
cd /home/frankbria/projects/podcastfy
git pull origin main
./deployment/scripts/deploy.sh
```

### Backup Database

```bash
# Manual backup
ssh root@47.88.89.175
sudo -u postgres pg_dump podcastfy | gzip > /var/backups/podcastfy-$(date +%Y%m%d).sql.gz
```

### View Logs

```bash
# Real-time monitoring
ssh root@47.88.89.175
journalctl -u podcastfy-api -f           # API logs
journalctl -u podcastfy-celery -f        # Celery logs
journalctl -u podcastfy-frontend -f      # Frontend logs
tail -f /var/www/podcastfy/logs/frontend-access.log  # Nginx access
```

## Support Resources

- **QUICKSTART.md**: Step-by-step deployment guide
- **DEPLOYMENT.md**: Comprehensive deployment documentation
- **README.md**: Deployment directory overview
- **GitHub Issues**: https://github.com/souzatharsis/podcastfy/issues

## Summary

**Deployment is ready to execute!**

1. ✅ All configuration files created
2. ✅ All scripts ready
3. ✅ All documentation complete
4. ⏳ Waiting for execution on server 47.88.89.175
5. ⏳ Waiting for domain name configuration

**Files ready for deployment:**
- `deployment/scripts/setup-server.sh` - Run once on server
- `deployment/scripts/deploy.sh` - Run for each deployment
- `deployment/nginx/podcastfy.conf` - Nginx configuration
- `deployment/systemd/*.service` - Service definitions
- `deployment/QUICKSTART.md` - Step-by-step guide
- `deployment/DEPLOYMENT.md` - Comprehensive docs

**Next immediate action:**
Transfer `deployment/` directory to server and execute `setup-server.sh`

---

**Server**: 47.88.89.175
**Target**: `/var/www/podcastfy/`
**Domain**: *To be provided*
**Branch**: `001-gui-podcast-studio`
