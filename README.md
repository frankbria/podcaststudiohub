# Podcastfy Studio Hub 🎙️

A multi-tenant SaaS platform for AI-generated podcasts, built on top of the open-source [Podcastfy](https://github.com/souzatharsis/podcastfy) package.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

Podcastfy Studio Hub is a full-stack web application that provides a user-friendly interface and multi-tenant architecture for generating AI-powered podcasts from various content sources. It wraps the powerful Podcastfy engine with:

- **User authentication and authorization** (session-based)
- **Project and episode management**
- **Asynchronous background processing** with Celery
- **Multi-tenant data isolation**
- **RESTful API** built with FastAPI
- **Modern web interface** built with Next.js
- **Production-ready deployment** for VPS hosting

## Architecture

This is a **monorepo** containing:

```
podcaststudiohub/
├── apps/
│   ├── api/              # FastAPI backend (Python)
│   └── web/              # Next.js frontend (TypeScript/React)
├── deployment/           # VPS deployment configurations
└── tests/                # E2E test suite (Playwright)
```

### Tech Stack

**Backend (FastAPI)**
- Python 3.11+
- FastAPI for API framework
- SQLAlchemy ORM with PostgreSQL
- Alembic for database migrations
- Celery + Redis for async task processing
- Bcrypt for password hashing
- Podcastfy v0.4.1 for podcast generation

**Frontend (Next.js)**
- Next.js 14 (App Router)
- TypeScript
- React 18
- Tailwind CSS + Shadcn/UI components
- NextAuth.js for authentication
- TanStack Query for data fetching

**Infrastructure**
- PostgreSQL 15 for database
- Redis for caching and task queue
- Nginx as reverse proxy
- Systemd for service management
- VPS deployment (Ubuntu/Debian)

## Features

### Core Podcast Generation
- Transform multi-modal content (websites, PDFs, images, YouTube) into engaging audio conversations
- Support for 100+ LLM models via LiteLLM (OpenAI, Anthropic, Google Gemini)
- Multiple TTS providers (OpenAI, ElevenLabs, Google, Edge TTS)
- Short-form (2-5 min) and long-form (30+ min) podcasts
- Multi-language support

### Platform Features
- **User Management**: Secure authentication with session management
- **Project Organization**: Group episodes into projects
- **Episode Management**: Create, track, and manage podcast episodes
- **Content Sources**: Support for URLs, files, and user-provided topics
- **Background Processing**: Async generation with progress tracking
- **Multi-tenant**: Complete data isolation per user
- **Storage**: Local filesystem with optional S3 integration

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 20 or higher
- PostgreSQL 15+
- Redis 7+
- FFmpeg (for audio processing)

### Local Development Setup

#### 1. Clone the Repository

```bash
git clone https://github.com/frankbria/podcaststudiohub.git
cd podcaststudiohub
```

#### 2. Set Up Backend (API)

```bash
cd apps/api

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (using uv for faster installs)
uv sync
# OR using pip
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your settings:
# - DATABASE_URL
# - REDIS_URL
# - JWT_SECRET_KEY
# - ENCRYPTION_KEY
# - API keys (OPENAI_API_KEY, GEMINI_API_KEY, etc.)

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, start Celery worker
celery -A src.worker worker --loglevel=info
```

#### 3. Set Up Frontend (Web)

```bash
cd apps/web

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env.local
# Edit .env.local with your settings:
# - NEXT_PUBLIC_API_URL=http://localhost:8000
# - NEXTAUTH_SECRET
# - NEXTAUTH_URL=http://localhost:3000

# Start development server
npm run dev
```

#### 4. Access the Application

- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/health

### Environment Variables

#### Backend (`apps/api/.env`)

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost/podcastfy

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
JWT_SECRET_KEY=<generate-with-openssl-rand-hex-32>
JWT_ALGORITHM=HS256
ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>

# API Settings
DEBUG=True
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000

# AI API Keys (users can override in their profiles)
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...

# Storage (optional S3)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=...
```

#### Frontend (`apps/web/.env.local`)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<generate-with-openssl-rand-hex-32>
```

## Production Deployment

Deployment to **47.88.89.175** (`/opt/podcaststudiohub/`) using **PM2** for process management.

### Automated Deployment (Recommended)

**GitHub Actions automatically deploys on push to `main`:**

```bash
git push origin main
```

The workflow (`.github/workflows/deploy-dev.yml`):
- Runs tests (API + Frontend)
- Builds Next.js frontend
- Syncs code via rsync
- Installs dependencies with `uv` and `npm`
- Runs database migrations
- Restarts PM2 processes
- Performs health checks

**Manual trigger in GitHub:**
1. Go to **Actions** tab
2. Select **Deploy to Development**
3. Click **Run workflow**

### Manual Deployment

For manual deployment that parallels the GitHub Actions workflow, see [`deployment/README.md`](deployment/README.md).

### Deployment Features

- **Process Manager**: PM2 for all services (API, Celery, Frontend)
- **Python Dependencies**: Managed with `uv`
- **Database Migrations**: Automated Alembic migrations
- **Nginx Reverse Proxy**: Routes traffic to PM2 processes
- **Health Checks**: Automated verification after deployment
- **SSL/TLS**: Configured for https://dev.podcaststudiohub.me

See [`deployment/README.md`](deployment/README.md) for complete deployment documentation and troubleshooting.

## Project Structure

```
podcaststudiohub/
├── apps/
│   ├── api/                          # FastAPI backend
│   │   ├── src/
│   │   │   ├── api/                  # API endpoints (routers)
│   │   │   ├── models/               # SQLAlchemy models
│   │   │   ├── schemas/              # Pydantic schemas
│   │   │   ├── services/             # Business logic
│   │   │   │   ├── auth_service.py   # Authentication
│   │   │   │   ├── podcast_service.py # Podcast generation
│   │   │   │   └── storage_service.py # File storage
│   │   │   ├── middleware/           # CORS, tenant context
│   │   │   ├── routers/              # API route handlers
│   │   │   ├── config.py             # Configuration
│   │   │   ├── database.py           # Database connection
│   │   │   ├── main.py               # FastAPI app
│   │   │   └── worker.py             # Celery worker
│   │   ├── alembic/                  # Database migrations
│   │   └── pyproject.toml            # Python dependencies
│   │
│   └── web/                          # Next.js frontend
│       ├── src/
│       │   ├── app/                  # App router pages
│       │   ├── components/           # React components
│       │   ├── lib/                  # Utilities
│       │   └── styles/               # CSS styles
│       └── package.json              # Node dependencies
│
├── deployment/                       # Deployment configs
│   ├── nginx/                        # Nginx configuration
│   ├── systemd/                      # Systemd service files
│   ├── scripts/                      # Deployment scripts
│   ├── QUICKSTART.md                 # Deployment guide
│   └── DEPLOYMENT.md                 # Full deployment docs
│
├── tests/                            # Test suite
│   ├── test_api.py                   # API tests
│   ├── test_auth.py                  # Auth tests
│   └── ...
│
├── data/                             # Runtime data
│   ├── audio/                        # Generated podcasts
│   └── transcripts/                  # Generated transcripts
│
├── .github/workflows/                # CI/CD workflows
│   └── deploy.yml                    # Deployment workflow
│
├── pyproject.toml                    # Root Python config (podcastfy)
├── package.json                      # Root Node config
├── docker-compose.yml                # Local development stack
├── CLAUDE.md                         # Claude Code instructions
└── README.md                         # This file
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `POST /api/auth/logout` - Logout user
- `GET /api/auth/me` - Get current user

### Projects
- `GET /api/projects` - List user's projects
- `POST /api/projects` - Create new project
- `GET /api/projects/{id}` - Get project details
- `PUT /api/projects/{id}` - Update project
- `DELETE /api/projects/{id}` - Delete project

### Episodes
- `GET /api/episodes` - List episodes
- `POST /api/episodes` - Create episode
- `GET /api/episodes/{id}` - Get episode details
- `PUT /api/episodes/{id}` - Update episode
- `DELETE /api/episodes/{id}` - Delete episode

### Content & Generation
- `POST /api/content/extract` - Extract content from source
- `POST /api/generate/podcast` - Generate podcast (async)
- `GET /api/generate/status/{task_id}` - Get generation status
- `GET /api/episodes/{id}/audio` - Download audio file

See full API documentation at http://localhost:8000/docs (when running locally).

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_api.py

# Run frontend tests
cd apps/web
npm test

# Run end-to-end tests with Playwright
npx playwright test
```

## Development Workflow

### Backend Development

```bash
cd apps/api

# Activate virtual environment
source .venv/bin/activate

# Install new dependency
uv add <package-name>

# Create database migration
alembic revision --autogenerate -m "Description"

# Run migration
alembic upgrade head

# Run tests
pytest

# Format code
black src/ tests/
ruff check src/ tests/
```

### Frontend Development

```bash
cd apps/web

# Install new dependency
npm install <package-name>

# Run development server
npm run dev

# Build for production
npm run build

# Run production build locally
npm start

# Lint
npm run lint
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- **Python**: Follow PEP 8, use Black formatter, type hints required
- **TypeScript**: Follow ESLint config, use Prettier formatter
- **Git**: Conventional commits preferred

## Upstream Podcastfy Package

This project is built on top of the excellent [Podcastfy](https://github.com/souzatharsis/podcastfy) package by Tharsis T. P. Souza. The core podcast generation engine (in the root directory) comes from that package.

### Syncing with Upstream

To update to a newer version of Podcastfy:

```bash
# See UPSTREAM_SYNC.md for detailed instructions
git remote add upstream https://github.com/souzatharsis/podcastfy.git
git fetch upstream
# Follow merge strategy in UPSTREAM_SYNC.md
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

The embedded Podcastfy package is also licensed under Apache 2.0.

## Acknowledgments

- [Podcastfy](https://github.com/souzatharsis/podcastfy) by Tharsis T. P. Souza - The core podcast generation engine
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Next.js](https://nextjs.org/) - React framework for production
- [Shadcn/UI](https://ui.shadcn.com/) - Beautiful UI components

## Support

- **Documentation**: See [`deployment/`](deployment/) directory for deployment docs
- **Issues**: Report bugs or request features via GitHub Issues
- **API Docs**: Available at `/docs` endpoint when API is running

---

**Server**: 47.88.89.175
**Repository**: https://github.com/frankbria/podcaststudiohub
**Upstream**: https://github.com/souzatharsis/podcastfy
