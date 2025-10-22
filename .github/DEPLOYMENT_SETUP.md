# GitHub Actions Deployment Setup

This document explains how to configure GitHub for automated deployments to the development environment.

## GitHub Environment Configuration

### 1. Create Development Environment

Go to your repository **Settings** → **Environments** → **New environment**

Name: `development`

### 2. Configure Environment Variables

In the `development` environment, add these **Variables**:

| Variable Name | Value | Description |
|--------------|-------|-------------|
| `SERVER_HOST` | `47.88.89.175` | Development server IP address |
| `SERVER_USER` | `root` | SSH user for deployment |
| `SERVER_PATH` | `/var/www/podcaststudiohub` | Application directory on server |
| `API_URL` | `https://dev.podcaststudiohub.me/api` | Public API URL |
| `FRONTEND_URL` | `https://dev.podcaststudiohub.me` | Public frontend URL |
| `NEXTAUTH_URL` | `https://dev.podcaststudiohub.me` | NextAuth.js callback URL |

### 3. Configure Environment Secrets

In the `development` environment, add these **Secrets**:

| Secret Name | How to Generate | Description |
|------------|-----------------|-------------|
| `SSH_PRIVATE_KEY` | See below | SSH private key for server access |
| `NEXTAUTH_SECRET` | `openssl rand -base64 32` | NextAuth.js encryption key |

## Generating SSH Key for Deployment

### On Your Local Machine

```bash
# Generate a new SSH key pair for GitHub Actions
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy

# Display the private key (copy this to GitHub Secret)
cat ~/.ssh/github_actions_deploy

# Display the public key (add this to server)
cat ~/.ssh/github_actions_deploy.pub
```

### On the Development Server

```bash
# SSH into the server
ssh root@47.88.89.175

# Add the public key to authorized_keys
echo "your-public-key-here" >> ~/.ssh/authorized_keys

# Ensure correct permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### Add Private Key to GitHub

1. Go to repository **Settings** → **Environments** → **development**
2. Click **Add secret**
3. Name: `SSH_PRIVATE_KEY`
4. Value: Paste the **entire private key** including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`

## Deployment Triggers

### Automatic Deployment

The workflow automatically deploys to development when:
- Code is pushed to the `main` branch
- Changes are in `apps/`, `deployment/`, or the workflow file itself

### Manual Deployment

You can manually trigger deployment:

1. Go to **Actions** tab in GitHub
2. Select **Deploy to Development** workflow
3. Click **Run workflow**
4. Choose whether to skip tests
5. Click **Run workflow**

## Deployment Process

When triggered, the workflow will:

1. ✅ **Checkout code** - Get latest code from repository
2. ✅ **Setup environments** - Python 3.12 + Node.js 20
3. ✅ **Install dependencies** - API (uv + pip) and frontend (npm)
4. ✅ **Run tests** - API tests (if not skipped)
5. ✅ **Build frontend** - Next.js production build
6. ✅ **Configure SSH** - Set up secure connection to server
7. ✅ **Deploy API** - Update code, dependencies, run migrations, restart service
8. ✅ **Deploy frontend** - Sync build, update runtime config, restart service
9. ✅ **Restart Celery** - Restart background worker
10. ✅ **Health check** - Verify API and frontend are responding
11. ✅ **Cleanup** - Remove SSH keys

## Monitoring Deployments

### View Deployment Status

- **Actions tab** shows all workflow runs
- **Environments** shows deployment history per environment
- Each deployment has a unique run ID and logs

### Deployment History

Go to **Settings** → **Environments** → **development** to see:
- When deployments happened
- Who triggered them
- Whether they succeeded or failed
- Links to workflow runs

## Troubleshooting

### Deployment Failed

1. Check the **Actions** tab for error logs
2. Common issues:
   - SSH connection failed → Verify SSH key is correct
   - Health check failed → Check service logs on server
   - Build failed → Check build errors in workflow logs

### Manual Server Check

```bash
# SSH into server
ssh root@47.88.89.175

# Check PM2 status
pm2 list

# Check service logs
pm2 logs podcaststudiohub-api --lines 50
pm2 logs podcaststudiohub-frontend --lines 50
pm2 logs podcaststudiohub-celery --lines 50

# Check API health
curl http://localhost:8001/health

# Check frontend
curl http://localhost:3003
```

### Rollback Deployment

If deployment breaks something:

```bash
# SSH into server
ssh root@47.88.89.175
cd /var/www/podcaststudiohub

# Rollback to previous commit
git log --oneline  # Find previous commit hash
git checkout <previous-commit-hash>

# Restart services
pm2 restart all
```

## Security Best Practices

✅ **SSH Key**: Use a dedicated key for GitHub Actions, not your personal key
✅ **Secrets**: Never commit secrets to the repository
✅ **Environment**: Use GitHub Environments to separate dev/prod secrets
✅ **Permissions**: Limit SSH user permissions on the server
✅ **Monitoring**: Review deployment logs regularly

## Future: Production Environment

When ready to deploy to production:

1. Create a `production` environment in GitHub
2. Add production-specific variables/secrets
3. Add protection rules:
   - Required reviewers before deployment
   - Wait timer (e.g., 10 minutes)
   - Restrict to `main` branch only
4. Create `deploy-prod.yml` workflow or extend this one

## Files Modified by This Workflow

**On Server:**
- `/var/www/podcaststudiohub/api/` - API code and dependencies
- `/var/www/podcaststudiohub/frontend/.next/` - Frontend build
- `/var/www/podcaststudiohub/frontend/public/config.js` - Runtime config
- Database migrations run automatically

**PM2 Services Restarted:**
- `podcaststudiohub-api`
- `podcaststudiohub-frontend`
- `podcaststudiohub-celery`

## Support

If you encounter issues:
1. Check workflow logs in GitHub Actions
2. Check server logs via SSH
3. Verify all secrets and variables are set correctly
4. Ensure SSH key is properly configured
