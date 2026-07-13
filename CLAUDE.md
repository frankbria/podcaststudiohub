# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Podcastfy Studio Hub** is a multi-tenant SaaS platform for AI-generated podcasts. It wraps the
open-source [Podcastfy](https://github.com/souzatharsis/podcastfy) generation engine (consumed as a
pinned **pip dependency** — see *Upstream Podcastfy Engine* below) with a full web application:
user accounts, projects/episodes, async generation, multi-tenant data isolation, and platform
distribution.

This is a **monorepo**: a FastAPI backend (`apps/api`), a Next.js frontend (`apps/web`), and VPS
deployment configs (`deployment/`).

## Architecture

```
podcaststudiohub/
├── apps/
│   ├── api/              # FastAPI backend (Python, uv)
│   │   ├── src/          # Application code (api, routers, services, tasks, models, schemas, middleware, utils)
│   │   ├── alembic/      # DB migrations (versions/ up to 017_…)
│   │   ├── tests/        # pytest + pytest-bdd
│   │   └── pyproject.toml
│   └── web/              # Next.js 15 frontend (TypeScript, App Router)
│       └── src/          # app/, components/, hooks/, lib/, types/, middleware.ts
├── deployment/           # VPS deploy: nginx/, scripts/, tests/, README.md (PM2 + nginx)
├── tests/e2e/            # Playwright end-to-end tests
├── docs/                 # Sphinx docs for the upstream engine + project guides
├── package.json          # Root npm scripts that orchestrate both apps
└── playwright.config.ts
```

### Backend (`apps/api`)

- **FastAPI** app at `src/main.py`; routers in `src/routers/`, business logic in `src/services/`.
- **SQLAlchemy (async) + PostgreSQL**; **Alembic** migrations in `apps/api/alembic/versions/`.
- **Celery + Redis** for async podcast generation; tasks in `src/tasks/` (the generation chain wraps
  the podcastfy engine), worker entry `src/worker.py`.
- **Auth is JWT** (HS256), not session-based. Config in `src/config.py` (`JWT_ALGORITHM = "HS256"`).
- **Multi-tenancy** via middleware in `src/middleware/` with per-tenant data isolation.

### Frontend (`apps/web`)

- **Next.js 15** App Router, TypeScript, **Tailwind + Shadcn/UI**, TanStack Query.
- Auth: the backend issues JWTs; authenticated browser calls and SSE go through a server-side
  `/api/proxy` Route Handler so the JWT is never exposed to the client.

### Upstream Podcastfy Engine

The podcast generation engine is the upstream `podcastfy` package, pinned as a **dependency** in
`apps/api/pyproject.toml` (`podcastfy==0.4.1`) — it is **not** vendored in this repo. The backend's
`src/services/` and `src/tasks/` call into it (content extraction, LLM transcript generation, TTS).

The pin is intentional: task kwargs are coupled to the upstream call signature (see #204). To upgrade,
bump the version in `apps/api/pyproject.toml`, run `uv sync`, and re-check the call signatures in
`src/services/` and `src/tasks/` before relying on it.

**0.4.2/0.4.3 were evaluated 2026-07-13 and deferred** (#363): 0.4.2+ imports `playwright` at module
top without declaring it (breaks app startup), offers no benefit to our call paths, and does not clear
the langchain CVEs on the pip-audit ignore list. See `apps/api/docs/podcastfy-0.4.3-evaluation.md` for
the full evaluation and re-evaluation triggers (chiefly: upstream langchain 1.x support).

Engine capabilities (provided by the dependency): multi-modal input (websites, YouTube, PDFs, images,
text, topics); 100+ LLMs via LiteLLM + Gemini; TTS via OpenAI, ElevenLabs, Gemini multi-speaker, and
Edge TTS; short-form and long-form ("content chunking with contextual linking") generation.

## Development Commands

Run from the repo root (root `package.json` orchestrates both apps):

```bash
# Run both apps (api on :8000, web on :3000)
npm run dev               # concurrently dev:api + dev:web
npm run dev:api           # uvicorn src.main:app --reload (cd apps/api)
npm run dev:web           # next dev (cd apps/web)

# Tests
npm run test              # api (pytest) + web (jest) + e2e (playwright)
npm run test:api          # cd apps/api && pytest
npm run test:web          # cd apps/web && npm run test
npm run test:e2e          # playwright test

# Lint
npm run lint              # ruff (api) + next lint (web)
```

Backend-only workflow uses `uv` (`cd apps/api && uv sync && uv run pytest`). Audio processing needs
`ffmpeg` installed on the host.

> Dev VPS note: the deployed dev host runs the API on `:8005` and web on `:3010` behind nginx; local
> defaults are `:8000` / `:3000`. See `deployment/README.md`.

## Configuration

- **`apps/api/.env.example`** — backend env (DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, `JWT_ALGORITHM=HS256`,
  ENCRYPTION_KEY, provider API keys). Copy to `apps/api/.env`.
- **Root `.env.example`** — full-stack reference (Postgres/Redis/NextAuth/Celery) for whole-stack setups.
- API keys: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `GOOGLE_CLOUD_CREDENTIALS` as needed
  by the chosen LLM/TTS providers.

## Code Style

- **Python**: PEP 8; ruff + mypy; tests with pytest / pytest-bdd. Manage deps with `uv add` / `uv remove`.
- **TypeScript**: Next.js conventions; Shadcn/UI + Tailwind; jest for unit, Playwright for e2e.

## CI/CD

GitHub Actions in `.github/workflows/` run lint + tests on PRs and deploy to the VPS (PM2 + nginx) on
merge. Deployment details and host hardening are documented in `deployment/README.md`.
