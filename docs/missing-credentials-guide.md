# Missing Credentials Guide

**Date:** 2025-11-11
**Status:** Requires User Action

## Overview

Based on environment configuration validation, several API credentials are missing or require configuration. This guide provides instructions on how to obtain and configure each missing credential.

---

## ✅ Working Services (No Action Required)

The following services are already configured and tested successfully:

| Service | Status | Notes |
|---------|--------|-------|
| **PostgreSQL Database** | ✅ Working | DATABASE_URL configured (verified in Task 1.1) |
| **Redis** | ✅ Working | Version 7.0.15, connection successful |
| **Google Gemini** | ✅ Working | 3 models available, API key valid |
| **OpenAI** | ✅ Working | 3 models available, API key valid |
| **ElevenLabs** | ✅ Working | 27 voices available, API key valid |

---

## ⚠️ Missing Credentials (Action Required)

### 1. AWS S3 Storage (MAJOR Priority)

**Status:** ❌ Missing
**Impact:** Podcast storage and download functionality blocked
**Required Variables:**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_BUCKET`
- `AWS_REGION` (default: us-east-1)

**How to Obtain:**

1. **Sign in to AWS Console:**
   - Navigate to https://console.aws.amazon.com/
   - Sign in with your AWS account (or create account if needed)

2. **Create IAM User for Application:**
   - Go to IAM → Users → Add User
   - User name: `podcaststudiohub-app`
   - Access type: ✅ Programmatic access
   - Permissions: Attach policy `AmazonS3FullAccess` (or create custom policy with S3 bucket access)

3. **Save Access Keys:**
   - After user creation, download CSV with:
     - Access Key ID (format: `AKIA...` followed by 16 chars)
     - Secret Access Key (format: 40-character alphanumeric string)
   - **Important:** Secret key shown only once - save immediately

4. **Create S3 Bucket (if not exists):**
   - Go to S3 → Create bucket
   - Bucket name: `podcaststudiohub-audio` (or your choice)
   - Region: `us-east-1` (or preferred region)
   - Block public access: Configure based on requirements (recommend blocking for security)
   - Enable versioning (recommended)

5. **Add to .env file:**
   ```bash
   AWS_ACCESS_KEY_ID=your-aws-access-key-id-here
   AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key-here
   AWS_S3_BUCKET=podcaststudiohub-audio
   AWS_REGION=us-east-1
   ```

**Security Best Practices:**
- ✅ Use IAM user with least privilege (S3-only access)
- ✅ Enable MFA on AWS root account
- ✅ Rotate access keys periodically
- ✅ Never commit .env files to git

---

### 2. NEXTAUTH_SECRET (CRITICAL Priority)

**Status:** ❌ Missing
**Impact:** Next.js authentication will not work
**Required Variable:** `NEXTAUTH_SECRET`

**How to Generate:**

1. **Generate secure random string:**
   ```bash
   # Option 1: Using openssl (recommended)
   openssl rand -base64 32

   # Option 2: Using python
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"

   # Option 3: Using online generator
   # Visit: https://generate-secret.vercel.app/32
   ```

2. **Add to .env files:**
   - Root `.env` (if using centralized config):
     ```bash
     NEXTAUTH_SECRET=your-generated-secret-here
     ```
   - Frontend `apps/web/.env.local` (create if missing):
     ```bash
     NEXTAUTH_SECRET=your-generated-secret-here
     NEXTAUTH_URL=http://localhost:3000
     NEXT_PUBLIC_API_URL=http://localhost:8000
     ```

**Important:**
- Use different secrets for dev/staging/prod environments
- Keep secret secure - treat like a password
- Never commit to version control

---

### 3. Transistor.fm API Key (MINOR Priority - New Scope)

**Status:** ❌ Missing (Expected)
**Impact:** Podcast distribution to Transistor.fm blocked (User Story 7)
**Required Variable:** `TRANSISTOR_API_KEY`

**How to Obtain:**

1. **Sign in to Transistor.fm:**
   - Navigate to https://transistor.fm
   - Sign in to your account (or create account if needed)
   - Plans start at $19/month for unlimited podcasts

2. **Generate API Key:**
   - Go to Account Settings → Developer
   - Or visit: https://dashboard.transistor.fm/api
   - Click "Create API Key" or "Generate New Key"
   - Copy the API key (format: Bearer token)

3. **Required Permissions:**
   - ✅ Show management
   - ✅ Episode upload
   - ✅ Metadata updates
   - ✅ Analytics access (optional)

4. **Add to .env file:**
   ```bash
   TRANSISTOR_API_KEY=your_transistor_api_key_here
   ```

**API Documentation:**
- Developer docs: https://developers.transistor.fm
- API reference: https://developers.transistor.fm/docs/api/

**Notes:**
- API key is optional if not using Transistor.fm distribution
- Alternative platforms: Spotify, Apple Podcasts (also need configuration)
- Consider RSS feed distribution as alternative

---

### 4. Frontend Environment Variables (MAJOR Priority)

**Status:** ❌ Missing
**Impact:** Frontend cannot connect to backend API
**Required File:** `apps/web/.env.local`

**Create File:**

Create `apps/web/.env.local` with the following content:

```bash
# Next.js Authentication
NEXTAUTH_SECRET=your-nextauth-secret-here
NEXTAUTH_URL=http://localhost:3000

# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000

# Application Settings
NODE_ENV=development
PORT=3000
```

**Important Notes:**
- `.env.local` is gitignored by default in Next.js projects
- `NEXT_PUBLIC_*` variables are exposed to browser - never put secrets here
- Server-side variables (like `NEXTAUTH_SECRET`) are safe from browser exposure

---

### 5. Application Configuration Variables (MAJOR Priority)

**Status:** ❌ Missing
**Impact:** May use defaults, but explicit configuration recommended

**Add to `apps/api/.env`:**
```bash
# Application server settings
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# Environment designation
NODE_ENV=development
PYTHONUNBUFFERED=1
```

These have sensible defaults but should be explicitly configured for clarity.

---

## 🔧 Optional/Future Credentials

### Google Cloud TTS (Alternative to ElevenLabs)

**Status:** ⚠️ Optional (ElevenLabs already configured)
**Variable:** `GOOGLE_CLOUD_CREDENTIALS`

If you want to use Google Cloud Text-to-Speech as an alternative:

1. Create Google Cloud project: https://console.cloud.google.com/
2. Enable Text-to-Speech API
3. Create service account and download JSON key
4. Set path in .env:
   ```bash
   GOOGLE_CLOUD_CREDENTIALS=/path/to/google-credentials.json
   ```

### Platform Distribution Keys (Spotify, Apple Podcasts)

**Status:** ⚠️ Optional (Future scope - User Story 7)
**Variables:**
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `APPLE_PODCASTS_KEY_ID`
- `APPLE_PODCASTS_KEY_SECRET`

These are for direct platform distribution in User Story 7. Can be configured later when implementing distribution features.

---

## 🔒 Security Checklist

Before adding credentials, verify:

- [ ] `.env` files are in `.gitignore`
- [ ] File permissions are restrictive (644 dev, 600 prod)
- [ ] No credentials hardcoded in source code
- [ ] Different secrets for dev/staging/prod environments
- [ ] Secrets stored securely (password manager, secrets vault)
- [ ] Team members have secure credential sharing method

### Verify .gitignore:

```bash
# Check .gitignore includes .env files
grep -E '\.env' /home/frankbria/projects/podcaststudiohub/.gitignore

# Verify .env files not tracked by git
git status --ignored | grep .env
```

---

## 📋 Quick Action Checklist

### Immediate (Critical Priority)
- [ ] Generate and add `NEXTAUTH_SECRET` to apps/web/.env.local
- [ ] Create `apps/web/.env.local` file with frontend variables
- [ ] Obtain AWS S3 credentials and add to apps/api/.env
- [ ] Create S3 bucket for podcast storage
- [ ] Add application configuration variables

### Soon (Major Priority)
- [ ] Obtain Transistor.fm API key (if using platform)
- [ ] Configure alternate platform keys (Spotify, Apple) if needed
- [ ] Test all services after adding credentials

### Later (Minor Priority)
- [ ] Set up Google Cloud TTS (if needed as ElevenLabs alternative)
- [ ] Configure production secrets management
- [ ] Implement environment-specific configs

---

## 🧪 Testing Credentials

After adding credentials, re-run the validation script:

```bash
cd apps/api
uv run python scripts/test_credentials.py
```

Expected output after adding missing credentials:
```
================================================================================
SUMMARY: 7/7 services working
================================================================================
```

---

## 📞 Support & Documentation

- **AWS S3:** https://docs.aws.amazon.com/s3/
- **NextAuth.js:** https://next-auth.js.org/
- **Transistor.fm API:** https://developers.transistor.fm
- **Google Cloud TTS:** https://cloud.google.com/text-to-speech
- **Spotify for Developers:** https://developer.spotify.com/
- **Apple Podcasts Connect:** https://podcastsconnect.apple.com/

---

## Questions or Issues?

If you encounter issues obtaining or configuring credentials:

1. Check service documentation links above
2. Verify .env file syntax (no spaces around `=`)
3. Restart application after adding credentials
4. Run credential test script to verify
5. Check application logs for specific error messages

---

**Last Updated:** 2025-11-11
**Next Review:** After adding missing credentials
