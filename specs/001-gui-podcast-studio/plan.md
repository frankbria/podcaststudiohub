# Implementation Plan: GUI Podcast Studio

**Branch**: `001-gui-podcast-studio` | **Date**: 2025-10-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-gui-podcast-studio/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Transform the existing CLI-based Podcastfy into a multi-tenant SaaS platform with a GUI. The system will enable non-technical users to generate podcast episodes from various content sources (URLs, PDFs, text), manage episode libraries, publish to S3 hosting, and distribute to podcast platforms (Spotify, Apple Podcasts) via a Next.js frontend with FastAPI backend. The architecture follows a monorepo pattern with separated frontend/backend deployments, reusing the existing podcast generation pipeline while adding multi-user support, persistent storage, and automated distribution capabilities.

## Technical Context

**Language/Version**:
- Frontend: TypeScript 5.x / Node.js 20.x
- Backend: Python 3.11+ (matching existing codebase)

**Primary Dependencies**:
- Frontend: Next.js 14.x, NextAuth.js (authentication), TanStack Query (API state), Shadcn UI (components)
- Backend: FastAPI 0.104+, Pydantic 2.x (validation), LiteLLM (existing), PyDub (existing)
- Database: PostgreSQL 15+ with JSONB, pgcrypto extension for credential encryption
- Auth/Security: NextAuth.js (frontend), JWT with RS256 (API), bcrypt (password hashing)
- Storage: AWS S3 SDK (boto3), file streaming
- Task Queue: Celery 5.3+ with Redis 5.0+ for background jobs
- Real-time Updates: Server-Sent Events (FastAPI StreamingResponse)
- Audio Processing: PyDub 0.25.1+ (existing), FFmpeg 1.4+ (audio merging, normalization, format conversion)

**Storage**:
- User data, projects, episodes, credentials (encrypted): PostgreSQL with JSONB + pgcrypto
- Generated audio files: Local filesystem + S3 (for published episodes)
- Audio snippets (intros, outros, midrolls, ads, music): S3 with metadata in PostgreSQL
- Episode compositions (merged audio with snippets): S3 + composition timeline in PostgreSQL
- Generated transcripts: PostgreSQL + optionally filesystem
- RSS feeds: S3 (static XML files)
- Task queue state: Redis

**Testing**:
- Frontend: Jest + React Testing Library, Playwright (E2E)
- Backend: pytest (existing), pytest-asyncio, httpx (API tests)
- Integration: Contract tests between frontend/backend APIs
- Database: pytest with PostgreSQL test containers
- Audio Processing: PyTest with sample audio files for snippet merging and normalization

**Target Platform**:
- Frontend: Vercel, Netlify, or Docker container (web server)
- Backend: Docker container on cloud platform (AWS ECS, GCP Cloud Run, or DigitalOcean)
- Multi-tenant, horizontally scalable

**Project Type**: Web application (monorepo with separated frontend/backend)

**Performance Goals**:
- API response time: <200ms for metadata operations, <2s for content extraction initiation
- Podcast generation: Maintain existing CLI performance (2-5 min for short-form)
- UI responsiveness: First contentful paint <1.5s, Time to interactive <3s
- Concurrent users: Support 100+ simultaneous users
- Database queries: <100ms for episode library queries with 1000+ episodes per user

**Constraints**:
- Must reuse existing CLI podcast generation logic (FR-015)
- API and frontend deployed to different URLs (separate CORS configuration)
- Multi-tenant data isolation (row-level or database-level)
- Secure credential storage (encrypted at rest)
- RSS feed compliance with Apple Podcasts/Spotify standards
- S3 upload bandwidth limits (consider chunked uploads for large files)

**Scale/Scope**:
- Initial deployment: 100-500 users
- Episodes per user: Up to 1000 episodes
- Concurrent podcast generation jobs: 10-20 simultaneous
- Storage: ~100GB initial (audio files in S3)
- API endpoints: ~30-40 REST endpoints
- Frontend pages: ~15-20 pages/views

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution Status**: No constitution file found at `.specify/memory/constitution.md` (file contains template only).

**Default Gates** (applied in absence of constitution):

- ✅ **Reuse existing code**: Feature spec explicitly requires reusing existing CLI functionality (FR-015)
- ⚠️ **Complexity justification needed**: Introducing multi-tenant SaaS architecture, database layer, authentication system, and frontend/backend separation adds significant complexity to existing CLI tool
- ✅ **Test coverage**: Existing codebase has pytest tests; plan includes frontend/backend/integration testing strategy
- ⚠️ **Deployment complexity**: Requires separate deployment for frontend (static hosting) and backend (Docker container), plus database, S3, and optional task queue

**Violations requiring justification** (see Complexity Tracking below):
1. Multi-tenant architecture (vs single-user CLI)
2. Database introduction (vs file-based storage)
3. Separate frontend/backend deployments

## Project Structure

### Documentation (this feature)

```
specs/001-gui-podcast-studio/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── openapi.yaml     # Backend API specification
│   └── types.ts         # Frontend TypeScript types (generated from OpenAPI)
├── checklists/
│   └── requirements.md  # Specification quality checklist (completed)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
podcastfy/                          # Existing CLI codebase (preserved)
├── client.py                       # Existing CLI entry point
├── content_generator.py            # Existing LLM generation
├── text_to_speech.py              # Existing TTS orchestration
├── content_parser/                 # Existing content extraction
├── tts/                            # Existing TTS providers
├── utils/                          # Existing config/logging
└── api/
    └── fast_app.py                 # Existing basic FastAPI endpoint

apps/
├── web/                            # Next.js frontend application
│   ├── src/
│   │   ├── app/                    # Next.js 14 App Router
│   │   │   ├── (auth)/            # Auth-protected routes
│   │   │   │   ├── dashboard/
│   │   │   │   ├── projects/
│   │   │   │   ├── episodes/
│   │   │   │   └── settings/
│   │   │   ├── api/               # API route handlers (NextAuth)
│   │   │   │   └── auth/
│   │   │   ├── login/
│   │   │   ├── signup/
│   │   │   └── layout.tsx
│   │   ├── components/            # React components
│   │   │   ├── ui/                # Shadcn UI primitives
│   │   │   ├── episodes/          # Episode-specific components
│   │   │   ├── projects/
│   │   │   └── layout/
│   │   ├── lib/                   # Utilities
│   │   │   ├── api-client.ts      # Backend API client
│   │   │   ├── auth.ts            # NextAuth configuration
│   │   │   └── utils.ts
│   │   └── types/                 # TypeScript types
│   │       └── api.ts             # Generated from OpenAPI spec
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.js
│   └── tailwind.config.js
│
└── api/                            # FastAPI backend application
    ├── src/
    │   ├── main.py                 # FastAPI app entry point
    │   ├── config.py               # Environment configuration
    │   ├── dependencies.py         # FastAPI dependency injection
    │   ├── middleware/
    │   │   ├── auth.py            # JWT verification middleware
    │   │   ├── tenant.py          # Multi-tenant context injection
    │   │   └── cors.py            # CORS configuration
    │   ├── models/                # Database models (SQLAlchemy)
    │   │   ├── user.py
    │   │   ├── project.py
    │   │   ├── episode.py
    │   │   ├── content_source.py
    │   │   ├── distribution_target.py
    │   │   ├── audio_snippet.py   # Audio snippet storage and metadata
    │   │   ├── episode_layout.py  # Reusable composition templates
    │   │   └── episode_composition.py # Episode-specific composition state
    │   ├── schemas/               # Pydantic request/response schemas
    │   │   ├── auth.py
    │   │   ├── project.py
    │   │   ├── episode.py
    │   │   ├── snippet.py         # Audio snippet request/response
    │   │   ├── composition.py     # Layout and composition schemas
    │   │   └── common.py
    │   ├── routers/               # API route handlers
    │   │   ├── auth.py            # POST /auth/register, /auth/login
    │   │   ├── projects.py        # CRUD for projects
    │   │   ├── episodes.py        # CRUD + generation
    │   │   ├── content.py         # Content source management
    │   │   ├── generation.py      # Podcast generation orchestration
    │   │   ├── snippets.py        # Audio snippet CRUD and upload
    │   │   ├── compositions.py    # Episode layout and composition management
    │   │   ├── publishing.py      # S3 upload, RSS generation
    │   │   └── distribution.py    # Platform distribution
    │   ├── services/              # Business logic
    │   │   ├── auth_service.py    # User authentication/registration
    │   │   ├── podcast_service.py # Wraps existing podcastfy CLI
    │   │   ├── storage_service.py # S3 interactions
    │   │   ├── rss_service.py     # RSS feed generation
    │   │   ├── distribution_service.py # Platform API integrations
    │   │   ├── audio_service.py   # Audio snippet management and metadata extraction
    │   │   └── composition_service.py # Episode composition and audio merging (PyDub/FFmpeg)
    │   ├── tasks/                 # Background task definitions (Celery)
    │   │   ├── podcast_generation.py
    │   │   ├── audio_composition.py   # Snippet merging and normalization
    │   │   ├── s3_upload.py
    │   │   └── platform_distribution.py
    │   └── utils/
    │       ├── encryption.py      # Credential encryption
    │       ├── jwt.py             # JWT token handling
    │       └── validators.py
    └── tests/
        ├── conftest.py
        ├── test_auth.py
        ├── test_projects.py
        ├── test_episodes.py
        ├── test_generation.py
        └── test_publishing.py

packages/                           # Shared packages (optional)
└── shared-types/                   # Shared TypeScript/Python types
    ├── podcast-types.ts
    └── api-contracts.json

tests/                              # Existing CLI tests (preserved)
├── test_client.py
├── test_content_parser.py
└── ...

data/                               # Runtime data (development)
├── audio/                          # Generated podcasts (local dev)
├── transcripts/                    # Generated transcripts
└── uploads/                        # User-uploaded documents

.docker/                            # Docker configurations
├── api.Dockerfile
├── web.Dockerfile
└── docker-compose.yml

.github/
└── workflows/
    ├── python-app.yml              # Existing CLI CI
    ├── api-tests.yml               # New backend CI
    └── web-tests.yml               # New frontend CI

package.json                        # Root package.json (monorepo scripts)
pyproject.toml                      # Existing Python dependencies
requirements.txt                    # Existing requirements
.env.example                        # Environment variables template
```

**Structure Decision**: Selected **Web application (Option 2)** monorepo structure with added `apps/` directory to separate frontend (`apps/web/`) and backend (`apps/api/`) while preserving the existing `podcastfy/` CLI codebase. The existing code remains functional as a standalone CLI tool, and the new API reuses its core functionality via service wrappers. Frontend and backend are independently deployable to different URLs as required.

## Complexity Tracking

*Violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Multi-tenant SaaS architecture | User input explicitly requires "multi-client SaaS framework", FR-006 requires persisting user projects, and the feature is designed for multiple users managing their own podcast libraries | Single-user deployment would contradict the SaaS requirement and prevent monetization/scalability. Existing CLI is single-user only. |
| Database introduction (PostgreSQL) | FR-006 requires persistent storage for projects/episodes, FR-016 requires secure credential storage, FR-021 requires search/filtering of episode libraries, and multi-tenant architecture requires user data isolation. FR-023/FR-024 require audio snippet metadata storage. | File-based storage (existing approach) cannot support multi-user queries, concurrent access, credential encryption, efficient search across 100+ episodes per user, or snippet library management. |
| Separate frontend/backend deployments | User input specifies "API and frontend are deployed to different URLs", which is a hard requirement. This also enables independent scaling and technology choices (Next.js vs FastAPI). | Monolithic deployment or Next.js API routes would violate the deployment requirement and prevent horizontal scaling of podcast generation (CPU-intensive) separately from UI serving. |
| Task queue for background processing | Podcast generation takes 2-5 minutes (SC-007), blocking HTTP requests for this duration would cause timeouts. SC-008 requires batch processing of 20+ episodes. Real-time progress updates (FR-005) require async job tracking. FR-026 requires background audio merging. | Synchronous API endpoints would timeout, prevent concurrent generation, and block UI. FastAPI BackgroundTasks may suffice initially, but Celery+Redis provides better reliability, retry logic, and progress tracking for long-running jobs (generation + audio composition). |
| Audio composition layer (snippets + layouts) | FR-023 through FR-030 require professional podcast branding with intros/outros/midrolls, reusable layouts, and AI-driven or manual snippet positioning. This elevates from basic content conversion to professional podcast production. | Simple audio concatenation would not support mid-roll positioning (percentage/timestamp), audio normalization (FR-030), preview generation (FR-028), or reusable templates (FR-029). PyDub/FFmpeg provide necessary audio manipulation capabilities. |

