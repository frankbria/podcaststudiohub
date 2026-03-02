#!/usr/bin/env bash
# setup-demo-vps.sh — Reference script for provisioning the demo verification VPS.
#
# This script is NOT run by CI. It documents the one-time setup for a dedicated
# VPS used by rm-review.yml to deploy PR branches and run automated verification
# via Claude Code + agent-browser.
#
# Safe to run on an existing box — skips components that are already installed
# and never overwrites existing config files (.env, SSH keys, etc.).
#
# Prerequisites:
#   - Ubuntu 22.04+ or 24.04 LTS VPS (2 vCPU, 4GB RAM recommended)
#   - Root or sudo access
#   - Internet connectivity
#
# After running this script, configure GitHub secrets/variables:
#   Secret: DEMO_VPS_SSH_KEY  — contents of /home/$USER/.ssh/github_actions_key (private)
#   Secret: DEMO_VPS_USER     — your username
#   Variable: DEMO_VPS_HOST   — VPS IP or hostname
#   Variable: DEMO_VPS_PATH   — "/srv/demo/repo"
set -euo pipefail

DEMO_USER="${DEMO_USER:-$(whoami)}"
DEMO_PATH="/srv/demo"
REPO_URL="https://github.com/frankbria/podcaststudiohub.git"

echo "=== Demo VPS Setup (idempotent) ==="
echo "User: $DEMO_USER"
echo "Path: $DEMO_PATH"

# ── 1. System packages ───────────────────────────────
echo ""
echo "--- Installing system packages ---"
sudo apt-get update
sudo apt-get install -y \
	build-essential \
	curl \
	git \
	jq \
	ffmpeg \
	postgresql-16 \
	redis-server \
	nginx \
	unzip

# Start and enable services
sudo systemctl enable --now postgresql redis-server

# ── 2. Create demo user (if not exists) ──────────────
echo ""
echo "--- Setting up demo user ---"
if ! id "$DEMO_USER" &>/dev/null; then
	sudo useradd -m -s /bin/bash "$DEMO_USER"
	sudo usermod -aG sudo "$DEMO_USER"
fi

# ── 3. Node.js via nvm ───────────────────────────────
echo ""
echo "--- Checking Node.js ---"
if sudo -u "$DEMO_USER" bash -c 'export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; command -v node' &>/dev/null; then
	echo "Node.js already installed, skipping nvm setup"
	sudo -u "$DEMO_USER" bash -c '
		export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
		echo "  node $(node --version), npm $(npm --version)"
		command -v pm2 &>/dev/null || npm install -g pm2
	'
else
	echo "Installing Node.js 20 via nvm..."
	sudo -u "$DEMO_USER" bash -c '
		curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
		export NVM_DIR="$HOME/.nvm"
		[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
		nvm install 20
		nvm alias default 20
		npm install -g pm2
	'
fi

# ── 4. Python 3.12 + uv ──────────────────────────────
echo ""
echo "--- Checking Python + uv ---"
if command -v python3.12 &>/dev/null; then
	echo "Python 3.12 already installed"
else
	echo "Installing Python 3.12..."
	sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
fi
if sudo -u "$DEMO_USER" bash -c 'export PATH="$HOME/.cargo/bin:$PATH"; command -v uv' &>/dev/null; then
	echo "uv already installed"
else
	echo "Installing uv..."
	sudo -u "$DEMO_USER" bash -c '
		curl -LsSf https://astral.sh/uv/install.sh | sh
		grep -q "cargo/bin" ~/.bashrc 2>/dev/null || echo "export PATH=\"\$HOME/.cargo/bin:\$PATH\"" >> ~/.bashrc
	'
fi

# ── 5. PostgreSQL demo database ──────────────────────
echo ""
echo "--- Creating demo database ---"
sudo -u postgres psql -c "CREATE USER demo_app WITH PASSWORD 'demo_password';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE podcastfy_demo OWNER demo_app;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE podcastfy_demo TO demo_app;" 2>/dev/null || true

# ── 6. Claude Code CLI ───────────────────────────────
echo ""
echo "--- Checking Claude Code CLI ---"
if sudo -u "$DEMO_USER" bash -c 'export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; command -v claude' &>/dev/null; then
	echo "Claude Code already installed:"
	sudo -u "$DEMO_USER" bash -c 'export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; claude --version 2>/dev/null || echo "  (version check unavailable)"'
else
	echo "Installing Claude Code CLI..."
	sudo -u "$DEMO_USER" bash -c '
		export NVM_DIR="$HOME/.nvm"
		[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
		npm install -g @anthropic-ai/claude-code
	'
fi

# ── 7. Playwright / agent-browser ─────────────────────
echo ""
echo "--- Checking Playwright + agent-browser ---"
if sudo -u "$DEMO_USER" bash -c 'export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; command -v agent-browser' &>/dev/null; then
	echo "agent-browser already installed"
else
	echo "Installing agent-browser..."
	sudo -u "$DEMO_USER" bash -c '
		export NVM_DIR="$HOME/.nvm"
		[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
		npm install -g agent-browser
	'
fi
# Ensure Playwright browsers are installed (safe to re-run)
sudo -u "$DEMO_USER" bash -c '
	export NVM_DIR="$HOME/.nvm"
	[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
	npx playwright install --with-deps chromium 2>/dev/null || echo "Playwright browsers already installed"
'

# ── 8. GitHub CLI ─────────────────────────────────────
echo ""
echo "--- Checking GitHub CLI ---"
if command -v gh &>/dev/null; then
	echo "GitHub CLI already installed: $(gh --version | head -1)"
else
	echo "Installing GitHub CLI..."
	curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
		| sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
		| sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
	sudo apt-get update
	sudo apt-get install -y gh
fi

# ── 9. SSH key for GitHub Actions ─────────────────────
echo ""
echo "--- Generating SSH keypair for GitHub Actions ---"
sudo -u "$DEMO_USER" bash -c '
	mkdir -p ~/.ssh
	chmod 700 ~/.ssh
	if [ ! -f ~/.ssh/github_actions_key ]; then
		ssh-keygen -t ed25519 -f ~/.ssh/github_actions_key -N "" -C "demo-vps-github-actions"
		cat ~/.ssh/github_actions_key.pub >> ~/.ssh/authorized_keys
		chmod 600 ~/.ssh/authorized_keys
		echo ""
		echo "=== IMPORTANT: Add this private key as GitHub secret DEMO_VPS_SSH_KEY ==="
		echo ""
		cat ~/.ssh/github_actions_key
		echo ""
		echo "=================================================================="
	fi
'

# ── 10. Clone repository ─────────────────────────────
echo ""
echo "--- Cloning repository ---"
sudo mkdir -p "$DEMO_PATH"
sudo chown "$DEMO_USER:$DEMO_USER" "$DEMO_PATH"
sudo -u "$DEMO_USER" bash -c "
	if [ ! -d $DEMO_PATH/repo/.git ]; then
		git clone $REPO_URL $DEMO_PATH/repo
	else
		echo 'Repo already cloned, pulling latest...'
		cd $DEMO_PATH/repo && git pull origin main
	fi
"

# ── 11. Environment file ─────────────────────────────
echo ""
echo "--- Checking environment file ---"
if [ -f "$DEMO_PATH/.env.demo" ]; then
	echo "Environment file already exists at $DEMO_PATH/.env.demo — not overwriting"
else
	echo "Creating environment template..."
	sudo -u "$DEMO_USER" bash -c "
		cat > $DEMO_PATH/.env.demo << 'ENVEOF'
# Demo VPS environment — fill in API keys
DATABASE_URL=postgresql+asyncpg://demo_app:demo_password@localhost:5432/podcastfy_demo
SECRET_KEY=demo-secret-key-change-me
ENCRYPTION_KEY=demo-encryption-key-00000000
JWT_SECRET_KEY=demo-jwt-secret-change-me
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Claude Code (set your actual key)
ANTHROPIC_API_KEY=

# Demo service ports (offset from dev to avoid conflicts)
API_PORT=8200
FRONTEND_PORT=3200
ENVEOF
		echo 'Created $DEMO_PATH/.env.demo — edit to add API keys'
	"
fi

# ── 12. PM2 ecosystem config for demo services ───────
echo ""
echo "--- Checking PM2 ecosystem config ---"
if [ -f "$DEMO_PATH/ecosystem.demo.config.js" ]; then
	echo "PM2 config already exists at $DEMO_PATH/ecosystem.demo.config.js — not overwriting"
else
	echo "Creating PM2 ecosystem config..."
fi
# Only write if it doesn't exist (the heredoc is inside the guard above)
if [ ! -f "$DEMO_PATH/ecosystem.demo.config.js" ]; then
sudo -u "$DEMO_USER" bash -c "
	cat > $DEMO_PATH/ecosystem.demo.config.js << 'PM2EOF'
module.exports = {
  apps: [
    {
      name: 'demo-api',
      cwd: '$DEMO_PATH/repo/apps/api',
      interpreter: 'none',
      script: '\$HOME/.cargo/bin/uv',
      args: 'run uvicorn src.main:app --host 0.0.0.0 --port 8200',
      env_file: '$DEMO_PATH/.env.demo',
    },
    {
      name: 'demo-web',
      cwd: '$DEMO_PATH/repo/apps/web',
      script: 'npm',
      args: 'start',
      env: {
        PORT: 3200,
        NEXT_PUBLIC_API_URL: 'http://localhost:8200',
      },
    },
    {
      name: 'demo-celery',
      cwd: '$DEMO_PATH/repo/apps/api',
      interpreter: 'none',
      script: '\$HOME/.cargo/bin/uv',
      args: 'run celery -A src.worker:celery_app worker --loglevel=info',
      env_file: '$DEMO_PATH/.env.demo',
    },
  ],
};
PM2EOF
"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. If new: edit $DEMO_PATH/.env.demo with actual API keys"
echo "  2. If new SSH key was generated: add it as GitHub secret DEMO_VPS_SSH_KEY"
echo "  3. Add GitHub secrets/variables (if not already set):"
echo "     - Secret: DEMO_VPS_USER = $DEMO_USER"
echo "     - Variable: DEMO_VPS_HOST = <this server's IP>"
echo "     - Variable: DEMO_VPS_PATH = $DEMO_PATH/repo"
echo "  4. Test: ssh $DEMO_USER@<host> 'claude --version'"
echo ""
echo "Components that were skipped (already installed) are safe to re-check."
