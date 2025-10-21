#!/bin/bash
# Podcastfy Deployment Script
# Run this from the project root to deploy to the server

set -e

SERVER="root@47.88.89.175"
PROJECT_ROOT="/var/www/podcastfy"

echo "===================================="
echo "Podcastfy Deployment"
echo "===================================="

# Check if we're in the project root
if [ ! -f "package.json" ] || [ ! -d "apps" ]; then
    echo "Error: Run this script from the project root"
    exit 1
fi

# Build Frontend
echo "Building frontend..."
cd apps/web
npm install
npm run build
cd ../..

# Deploy Frontend
echo "Deploying frontend..."
ssh $SERVER "mkdir -p $PROJECT_ROOT/frontend"
rsync -avz --delete \
    --exclude 'node_modules' \
    --exclude '.next/cache' \
    apps/web/ $SERVER:$PROJECT_ROOT/frontend/

# Deploy API
echo "Deploying API..."
ssh $SERVER "mkdir -p $PROJECT_ROOT/api"
rsync -avz --delete \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    apps/api/ $SERVER:$PROJECT_ROOT/api/

# Deploy shared dependencies
echo "Deploying shared code..."
rsync -avz podcastfy/ $SERVER:$PROJECT_ROOT/api/podcastfy/

# Install Python dependencies
echo "Installing Python dependencies on server..."
ssh $SERVER << 'ENDSSH'
cd /var/www/podcastfy/api
source .venv/bin/activate
pip install --upgrade pip
pip install -r ../../requirements.txt
pip install -e /var/www/podcastfy/api/podcastfy
deactivate
ENDSSH

# Install Node dependencies on server
echo "Installing Node dependencies on server..."
ssh $SERVER << 'ENDSSH'
cd /var/www/podcastfy/frontend
npm ci --production
ENDSSH

# Run database migrations
echo "Running database migrations..."
ssh $SERVER << 'ENDSSH'
cd /var/www/podcastfy/api
source .venv/bin/activate
alembic upgrade head
deactivate
ENDSSH

# Set permissions
echo "Setting permissions..."
ssh $SERVER "chown -R www-data:www-data $PROJECT_ROOT"

# Restart services
echo "Restarting services..."
ssh $SERVER << 'ENDSSH'
systemctl restart podcastfy-api
systemctl restart podcastfy-celery
systemctl restart podcastfy-frontend
systemctl reload nginx
ENDSSH

# Check service status
echo "Checking service status..."
ssh $SERVER << 'ENDSSH'
echo "API Status:"
systemctl status podcastfy-api --no-pager | head -5

echo "Celery Status:"
systemctl status podcastfy-celery --no-pager | head -5

echo "Frontend Status:"
systemctl status podcastfy-frontend --no-pager | head -5

echo "Nginx Status:"
systemctl status nginx --no-pager | head -5
ENDSSH

echo "===================================="
echo "Deployment complete!"
echo "===================================="
echo ""
echo "Application URLs:"
echo "Frontend: http://YOUR_DOMAIN"
echo "API: http://YOUR_DOMAIN/api"
echo "API Docs: http://YOUR_DOMAIN/api/docs"
echo ""
echo "Check logs:"
echo "  API: journalctl -u podcastfy-api -f"
echo "  Celery: journalctl -u podcastfy-celery -f"
echo "  Frontend: journalctl -u podcastfy-frontend -f"
echo "  Nginx: tail -f /var/www/podcastfy/logs/frontend-access.log"
echo ""
