#!/bin/bash
# Podcastfy Server Setup Script
# Run this script on the server to set up the initial infrastructure

set -e

echo "===================================="
echo "Podcastfy Server Setup"
echo "===================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

# Create application directories
echo "Creating application directories..."
mkdir -p /var/www/podcastfy/{frontend,api,logs,ssl,uploads}
chown -R www-data:www-data /var/www/podcastfy
chmod -R 755 /var/www/podcastfy

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    postgresql-15 \
    postgresql-contrib \
    redis-server \
    nginx \
    certbot \
    python3-certbot-nginx \
    nodejs \
    npm \
    ffmpeg \
    git

# Install Node.js 20 (LTS)
echo "Installing Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Start and enable services
echo "Starting services..."
systemctl start postgresql
systemctl enable postgresql
systemctl start redis-server
systemctl enable redis-server
systemctl start nginx
systemctl enable nginx

# Create PostgreSQL database
echo "Setting up PostgreSQL database..."
sudo -u postgres psql -c "CREATE DATABASE podcastfy;" || echo "Database already exists"
sudo -u postgres psql -c "CREATE USER podcastfy_user WITH PASSWORD 'CHANGE_THIS_PASSWORD';" || echo "User already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE podcastfy TO podcastfy_user;"

# Configure Redis
echo "Configuring Redis..."
sed -i 's/^# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf
sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
systemctl restart redis-server

# Create Python virtual environment for API
echo "Setting up Python virtual environment..."
cd /var/www/podcastfy/api
python3.11 -m venv .venv
chown -R www-data:www-data .venv

# Copy Nginx configuration
echo "Copying Nginx configuration..."
cp /tmp/podcastfy.conf /etc/nginx/sites-available/podcastfy
ln -sf /etc/nginx/sites-available/podcastfy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
nginx -t

# Create environment file templates
echo "Creating environment file templates..."
cat > /var/www/podcastfy/api/.env.template << 'EOF'
# Database
DATABASE_URL=postgresql://podcastfy_user:CHANGE_THIS_PASSWORD@localhost/podcastfy

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
ENCRYPTION_KEY=GENERATE_RANDOM_KEY_HERE
JWT_SECRET_KEY=GENERATE_RANDOM_JWT_KEY_HERE
JWT_ALGORITHM=RS256

# API Keys (Optional - users can provide their own)
OPENAI_API_KEY=
GEMINI_API_KEY=
ELEVENLABS_API_KEY=

# AWS S3 (Optional)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=

# Application
DEBUG=False
LOG_LEVEL=INFO
EOF

cat > /var/www/podcastfy/frontend/.env.local.template << 'EOF'
NEXT_PUBLIC_API_URL=http://YOUR_DOMAIN/api
NEXTAUTH_URL=http://YOUR_DOMAIN
NEXTAUTH_SECRET=GENERATE_RANDOM_SECRET_HERE
EOF

echo "===================================="
echo "Server setup complete!"
echo "===================================="
echo ""
echo "Next steps:"
echo "1. Edit /var/www/podcastfy/api/.env.template with your settings"
echo "2. Copy to /var/www/podcastfy/api/.env"
echo "3. Edit /var/www/podcastfy/frontend/.env.local.template"
echo "4. Copy to /var/www/podcastfy/frontend/.env.local"
echo "5. Deploy application code using deploy.sh"
echo "6. Configure SSL with: certbot --nginx -d YOUR_DOMAIN"
echo ""
