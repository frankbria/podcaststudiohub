# Quickstart Guide: GUI Podcast Studio Development

**Feature**: 001-gui-podcast-studio
**Last Updated**: 2025-10-20

This guide gets you running locally in under 15 minutes.

---

## Prerequisites

- **Python 3.11+** (existing CLI requirement)
- **Node.js 20.x** (for Next.js frontend)
- **Docker & Docker Compose** (for PostgreSQL and Redis)
- **uv** (Python package manager, already configured)
- **Git** (for version control)

---

## Quick Start (5 Minutes)

### 1. Clone and Setup (2 min)

```bash
# Clone repository
git clone <repo-url>
cd podcastfy

# Checkout feature branch
git checkout 001-gui-podcast-studio

# Install Python dependencies (existing CLI)
uv pip install -r requirements.txt

# Install frontend dependencies
cd apps/web
npm install
cd ../..

# Install backend dependencies
cd apps/api
uv pip install -r requirements.txt
cd ../..
```

### 2. Start Infrastructure (1 min)

```bash
# Start PostgreSQL + Redis via Docker Compose
docker-compose up -d postgres redis

# Verify services
docker-compose ps
```

### 3. Initialize Database (1 min)

```bash
# Run Alembic migrations
cd apps/api
alembic upgrade head

# (Optional) Seed test data
python scripts/seed_db.py
cd ../..
```

### 4. Start Services (1 min)

**Terminal 1 - Backend API:**
```bash
cd apps/api
uvicorn src.main:app --reload --port 8000
```

**Terminal 2 - Celery Worker:**
```bash
cd apps/api
celery -A src.worker worker --loglevel=info
```

**Terminal 3 - Frontend:**
```bash
cd apps/web
npm run dev
```

**Terminal 4 - Flower (Optional - Task Monitoring):**
```bash
cd apps/api
celery -A src.worker flower --port=5555
```

### 5. Access Applications

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000/docs (OpenAPI docs)
- **Flower Dashboard**: http://localhost:5555 (Celery tasks)

---

## Environment Variables

Create `.env` files in project root:

```bash
# .env (root)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/podcastfy
REDIS_URL=redis://localhost:6379/0
ENCRYPTION_KEY=your-32-char-encryption-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
JWT_ALGORITHM=RS256

# Existing Podcastfy API keys (reused from CLI)
GEMINI_API_KEY=<your-key>
OPENAI_API_KEY=<your-key>
ELEVENLABS_API_KEY=<your-key>

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
AWS_REGION=us-east-1
S3_BUCKET_NAME=podcastfy-episodes
```

```bash
# apps/web/.env.local (Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-nextauth-secret
```

---

## Development Workflow

### Running Tests

**Backend tests:**
```bash
cd apps/api
pytest tests/ -v
pytest tests/test_episodes.py::test_generate_podcast -v  # Single test
```

**Frontend tests:**
```bash
cd apps/web
npm test
npm run test:e2e  # Playwright E2E tests
```

**Existing CLI tests (still work):**
```bash
pytest tests/ -n auto
```

### Database Management

**Create new migration:**
```bash
cd apps/api
alembic revision --autogenerate -m "Add distribution targets table"
```

**Apply migrations:**
```bash
alembic upgrade head
```

**Rollback:**
```bash
alembic downgrade -1
```

**Reset database:**
```bash
alembic downgrade base
alembic upgrade head
python scripts/seed_db.py
```

### Code Generation

**Generate TypeScript types from OpenAPI:**
```bash
cd apps/web
npm run generate:types
# Outputs to src/types/api.ts
```

**Update SQLAlchemy models from schema:**
```bash
cd apps/api
python scripts/sync_models.py
```

---

## Project Structure Quick Reference

```
podcastfy/                      # Existing CLI (preserved)
├── client.py
├── content_generator.py
└── ...

apps/
├── web/                        # Next.js frontend
│   ├── src/app/               # App Router pages
│   ├── src/components/        # React components
│   └── src/lib/api-client.ts  # Backend API client
│
└── api/                        # FastAPI backend
    ├── src/
    │   ├── main.py            # FastAPI app
    │   ├── routers/           # API endpoints
    │   ├── models/            # SQLAlchemy models
    │   ├── schemas/           # Pydantic schemas
    │   └── services/          # Business logic
    └── tests/                 # Backend tests

.docker/                        # Docker configs
├── api.Dockerfile
└── docker-compose.yml
```

---

## Common Tasks

### 1. Create New User

**Via API:**
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "full_name": "Test User"
  }'
```

**Via Frontend:**
- Navigate to http://localhost:3000/signup
- Fill registration form

### 2. Generate Podcast

**Via API:**
```bash
# 1. Login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}' \
  | jq -r '.access_token')

# 2. Create project
PROJECT_ID=$(curl -X POST http://localhost:8000/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Podcast",
    "podcast_metadata": {
      "show_title": "Tech Insights",
      "author": "Test User",
      "description": "A tech podcast",
      "category": "Technology"
    }
  }' | jq -r '.id')

# 3. Create episode
EPISODE_ID=$(curl -X POST http://localhost:8000/projects/$PROJECT_ID/episodes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "title": "Episode 1",
      "description": "First episode",
      "format": "conversation"
    }
  }' | jq -r '.id')

# 4. Add content source
curl -X POST http://localhost:8000/episodes/$EPISODE_ID/content \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "url",
    "source_data": {"url": "https://example.com/article"}
  }'

# 5. Generate podcast
TASK_ID=$(curl -X POST http://localhost:8000/episodes/$EPISODE_ID/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | jq -r '.task_id')

# 6. Monitor progress (SSE)
curl -N http://localhost:8000/episodes/$EPISODE_ID/progress \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Monitor Background Tasks

**Flower Dashboard:**
- Open http://localhost:5555
- View active workers, task success/failure rates
- Inspect task details and retries

**Celery CLI:**
```bash
# List active tasks
celery -A src.worker inspect active

# Check worker status
celery -A src.worker inspect stats
```

### 4. Check Database

**Via psql:**
```bash
docker exec -it podcastfy-postgres psql -U postgres -d podcastfy

# List tables
\dt

# Query episodes
SELECT id, metadata->>'title', generation_status FROM episodes;

# Check RLS policies
\d+ episodes
```

**Via pgAdmin (Optional):**
```bash
docker run -p 5050:80 \
  -e 'PGADMIN_DEFAULT_EMAIL=admin@example.com' \
  -e 'PGADMIN_DEFAULT_PASSWORD=admin' \
  dpage/pgadmin4
```

---

## Debugging Tips

### Backend API Errors

**Enable debug logging:**
```python
# apps/api/src/config.py
LOG_LEVEL = "DEBUG"
```

**Check logs:**
```bash
# API logs (uvicorn)
tail -f apps/api/logs/api.log

# Celery worker logs
tail -f apps/api/logs/celery.log
```

**Use FastAPI interactive docs:**
- Navigate to http://localhost:8000/docs
- Test endpoints with built-in UI
- View request/response schemas

### Frontend Errors

**Check Next.js dev server:**
```bash
cd apps/web
npm run dev -- --turbo  # Faster with Turbo
```

**View React DevTools:**
- Install React DevTools browser extension
- Inspect component state and props

**Network debugging:**
- Open browser DevTools → Network tab
- Filter by "XHR" to see API calls
- Check request/response bodies

### Database Issues

**Connection errors:**
```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Check connection
docker exec podcastfy-postgres pg_isready
```

**Migration conflicts:**
```bash
# Stamp current revision
alembic stamp head

# Or reset entirely
alembic downgrade base
alembic upgrade head
```

### Celery Task Failures

**Retry failed task:**
```bash
celery -A src.worker inspect active
celery -A src.worker control revoke <task-id>
```

**Check Redis queue:**
```bash
docker exec -it podcastfy-redis redis-cli
KEYS *
LLEN celery  # Queue length
```

---

## Next Steps

1. **Read the spec**: `specs/001-gui-podcast-studio/spec.md`
2. **Review data model**: `specs/001-gui-podcast-studio/data-model.md`
3. **Check API contracts**: `specs/001-gui-podcast-studio/contracts/openapi.yaml`
4. **Explore research decisions**: `specs/001-gui-podcast-studio/research.md`

---

## Troubleshooting

### Port Conflicts

```bash
# Check what's using ports
lsof -i :3000  # Next.js
lsof -i :8000  # FastAPI
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis

# Kill process
kill -9 <PID>
```

### Docker Issues

```bash
# Stop all containers
docker-compose down

# Remove volumes (reset data)
docker-compose down -v

# Rebuild images
docker-compose build --no-cache
```

### Module Not Found

```bash
# Backend
cd apps/api
uv pip install -r requirements.txt

# Frontend
cd apps/web
rm -rf node_modules package-lock.json
npm install
```

---

## Support

- **Documentation**: See `specs/001-gui-podcast-studio/` directory
- **API Docs**: http://localhost:8000/docs (when running)
- **Issues**: Report bugs in project issue tracker
