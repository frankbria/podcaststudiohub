# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Podcastfy Studio Hub** is a multi-tenant SaaS platform for AI-generated podcasts: an in-repo
generation engine (`apps/api/src/engine/`, see below) inside a full web application: user accounts,
projects/episodes, async generation, multi-tenant data isolation, and platform distribution. It began
as a wrapper around the open-source [Podcastfy](https://github.com/souzatharsis/podcastfy) package;
that dependency was removed in #543.

This is a **monorepo**: a FastAPI backend (`apps/api`), a Next.js frontend (`apps/web`), and VPS
deployment configs (`deployment/`).

## Architecture

```
podcaststudiohub/
├── apps/
│   ├── api/              # FastAPI backend (Python, uv)
│   │   ├── src/          # Application code (api, routers, services, tasks, models, schemas, middleware, utils, engine)
│   │   ├── alembic/      # DB migrations (versions/ up to 018_…)
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
- **Celery + Redis** for async podcast generation; tasks in `src/tasks/` (the generation chain runs
  the in-repo engine), worker entry `src/worker.py`.
- **Auth is JWT** (HS256), not session-based. Config in `src/config.py` (`JWT_ALGORITHM = "HS256"`).
- **Multi-tenancy** via middleware in `src/middleware/` with per-tenant data isolation.

### Frontend (`apps/web`)

- **Next.js 15** App Router, TypeScript, **Tailwind + Shadcn/UI**, TanStack Query.
- Auth: the backend issues JWTs; authenticated browser calls and SSE go through a server-side
  `/api/proxy` Route Handler so the JWT is never exposed to the client.

**The auth library question was settled 2026-09-08 (#442): stay on `next-auth` v4.** next-auth is a
thin shim here — FastAPI owns identity entirely, and next-auth only holds the backend JWT in an
httpOnly cookie, backs `useSession()`, and backs `getToken()` for route-gating and the proxy. v4
formally supports Next 16 / React 19 and is still patched; Auth.js v5 never left `beta` and is in
security-patch mode; Better Auth requires a database it owns, which FastAPI already owns. See
`apps/web/docs/auth-direction-evaluation.md` for the full evaluation and the two re-evaluation
triggers (chiefly: wanting social login / SSO / 2FA / passkeys).

### Generation engine (`apps/api/src/engine/`)

The live generation path (epic #538): `generate_podcast_task` calls it directly.

- **Script** (#541): `generate_script(sources, config, longform)` returns a validated Pydantic
  `Script` (`turns: list[Turn(speaker, text)]` plus title/summary) by calling the provider SDKs
  (`google-genai`, `openai`) directly for structured JSON. Prompts live in `src/engine/prompts/*.md`,
  versioned here; nothing is fetched at runtime. Long-form chunks carry a rolling summary, not the
  whole prior transcript. Fast provider failures (429/5xx/dropped connections) are retried in place
  so a blip does not discard paid chunks; timeouts are not (#574).
- **Voice** (#542): `src/engine/tts/` has five backends (`openai`, `elevenlabs` with Eleven v3
  Text-to-Dialogue, `gemini`, `gemini_multi`, `edge`) behind one `TTSBackend`; every temp file goes
  under a caller-supplied `workdir`, and there are no module-global API keys.
- **Task** (#543): reads the episode's **stored** TTS provider and raw config from the row (episode,
  else project default, else openai echo/shimmer), checks the voices before any paid call, fetches
  pending URL sources through the SSRF-guarded `ContentExtractionService.fetch_url_text` (YouTube
  URLs yield the video transcript), then scripts, voices, and `persist_transcript`s, which fills
  `episodes.transcript_path` (an S3 key under `podcasts/user-*/`, or a local path without a bucket).
  The router still sends a podcastfy-shaped `tts_model`/`text_to_speech`; the task ignores them
  (removal needs the `generate_podcast` endpoint split first, #623).
- Text extraction (HTML/PDF) lives in `src/services/text_extraction.py`.

Models come from `ENGINE_GEMINI_MODEL` / `ENGINE_OPENAI_MODEL` in `src/config.py`; a wrong model id
fails no test (every test fakes the SDK boundary), so changing one needs a live smoke call.

Nothing may bring back podcastfy's dependency tree: `tests/test_dependency_reachability.py` fails if
`podcastfy`, `langchain*`, `langsmith` or `litellm` is installed, or if `src/engine/` imports them.
`apps/api/scripts/pip_audit_gate.py` blocks on every advisory; its allowlists are empty. The
`apps/api/docs/podcastfy-*.md` analyses are kept as history.

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

# Lint  (also gated in CI by the "Lint (ruff + eslint)" job)
npm run lint              # lint:api + lint:web
npm run lint:api          # cd apps/api && uv run ruff check .
npm run lint:web          # cd apps/web && eslint .
```

Ruff's rule set is pinned in `apps/api/pyproject.toml` (`[tool.ruff.lint] select`) rather than
inherited: ruff's defaults widen between releases, so an unpinned set lets a routine version bump
redefine what "lint passes" means. Adopting further rules is a deliberate edit there.

`next lint` is gone — it was removed in Next 16, so `apps/web` invokes eslint directly against
`apps/web/eslint.config.mjs` (flat config; ESLint 10 dropped `.eslintrc.json` entirely). The
`no-restricted-imports` guard on `lucide-react` in that file is what enforces the Hugeicons-only
policy in `apps/web/CLAUDE.md` — keep it through any config change.

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
