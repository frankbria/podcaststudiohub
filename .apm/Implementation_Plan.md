# Podcast Studio Hub – Implementation Plan

**Memory Strategy:** Dynamic-MD (directory structure with Markdown logs)
**Last Modification:** 2025-11-11 - Phase 1 completed by Agent_Assessment_Foundation
**Project Overview:** Podcast Studio Hub is a multi-show podcast production platform that transforms content (URLs, PDFs, documents) into AI-generated audio conversations using Podcastfy, with quality-controlled script generation (Gemini LLM), ElevenLabs TTS, template-based audio composition, and automated publishing to Transistor.fm. The platform manages multiple themed shows with unique voice configurations, audio assets (intros/outros/midrolls), and provides AI pre-screening + human review workflows to ensure script quality before publication.

---

## Phase 1: Assessment & Foundation ✅ COMPLETED (2025-11-11)

### Task 1.1 – Smoke Test Current Deployment │ Agent_Assessment_Foundation ✅ COMPLETED

- **Objective:** Verify functional status of deployed application at dev.podcaststudiohub.me to establish baseline understanding of working features, broken components, and implementation gaps before planning new development work.
- **Output:** Comprehensive smoke test report documenting: (1) accessible frontend routes and console error status, (2) API endpoint inventory with health check results, (3) authentication flow status (registration/login functionality), (4) database connectivity and schema validation status, (5) gap analysis comparing deployed state against specs/001-gui-podcast-studio/spec.md requirements with prioritized feature list.
- **Guidance:** Application deployed to staging VPS (8 vCPU, 16GB RAM) with unknown functional status per Context Synthesis. CI/CD pipeline functional (GitHub rsync deployment) but features never tested. Testing must cover frontend (dev.podcaststudiohub.me), backend API (dev.podcaststudiohub.me/api), authentication mechanisms, and PostgreSQL database connectivity. Prioritize identifying critical gaps (missing core features) vs cosmetic issues. Report informs all subsequent implementation decisions.
- **Beads Issue:** podcaststudiohub-p7k | **Status:** Closed | **Completion Date:** 2025-11-11
- **Key Findings:** Frontend serving correctly, API infrastructure operational, critical authentication failure identified (JWT/database issue)

1. **Test frontend deployment:** Navigate to dev.podcaststudiohub.me, verify page loads successfully without critical errors, inspect browser console for JavaScript errors or warnings, identify accessible routes through navigation exploration, document any broken pages or 404 errors, note UI framework indicators (Next.js hydration, React DevTools visibility).
2. **Test API endpoints:** Access dev.podcaststudiohub.me/api health check endpoint, verify API responsiveness and basic connectivity, navigate to /docs route to test OpenAPI documentation availability (FastAPI auto-generated), attempt sample endpoint calls (if documented) to validate API contract implementation, document available vs missing endpoints from OpenAPI specification.
3. **Test authentication flow:** Attempt user registration via /auth/register endpoint (if accessible through UI or direct API call), test login functionality via /auth/login with test credentials, verify JWT token generation and validation in response, check for secure token storage mechanisms (localStorage, httpOnly cookies), document authentication implementation status and any security concerns.
4. **Test database connectivity:** Verify PostgreSQL connection from API layer (check API logs or database connection endpoints if available), query database to list existing tables, compare table existence against 11-table schema from specs/001-gui-podcast-studio/data-model.md, identify schema discrepancies (missing tables, unexpected tables), note any RLS policies or migration artifacts present.
5. **Compile smoke test report:** Document all findings in structured markdown report including: (1) Working Features section listing functional components, (2) Broken/Missing Features section with severity classification (critical/major/minor), (3) Gap Analysis comparing deployed state to spec.md functional requirements FR-001 through FR-030, (4) Recommended prioritization for addressing gaps based on dependency analysis, (5) Technical debt assessment identifying quick wins vs major refactors needed.

### Task 1.2 – Database Schema Assessment │ Agent_Assessment_Foundation ✅ COMPLETED

- **Objective:** Validate deployed PostgreSQL database schema matches specifications in specs/001-gui-podcast-studio/data-model.md, identify discrepancies requiring migration or reset, and establish database migration strategy that leverages fresh migration acceptability per Context Synthesis.
- **Output:** Database schema comparison report detailing: (1) complete inventory of existing tables/columns/indexes/constraints, (2) side-by-side comparison against data-model.md 11-table specification highlighting missing/extra/misaligned components, (3) assessment of existing Alembic migrations (if present), (4) recommended migration strategy (fresh reset vs incremental migrations) with justification, (5) User confirmation on database reset approach if major discrepancies found.
- **Guidance:** Depends on: Task 1.1 Output (database connectivity confirmation and table inventory). Context Synthesis confirms fresh database migrations acceptable with no production data preservation requirements. Data-model.md defines 11 tables: users, projects, episodes, content_sources, conversation_templates, tts_configurations, distribution_targets, rss_feeds, audio_snippets, episode_layouts, episode_compositions. Schema includes JSONB columns, Row-Level Security policies, pgcrypto encryption, and complex indexing strategy. If schema completely unrecognizable, use ad-hoc delegation for investigation. Validation must confirm RLS policies, triggers (updated_at), indexes (tenant_id, JSONB GIN), and constraints match specification.
- **Beads Issue:** podcaststudiohub-858 | **Status:** Closed | **Completion Date:** 2025-11-11
- **Key Findings:** Alembic migrations 100% spec-compliant, SQLAlchemy models have major conflicts, recommended fresh database reset

1. **Ad-Hoc Delegation – Database schema investigation:** (Optional: .claude/commands/apm-8-delegate-debug.md) If Task 1.1 reveals completely unrecognizable schema or unexpected database structure requiring deep investigation before comparison can proceed, delegate detailed schema analysis to Ad-Hoc Agent to understand deployment history, migration artifacts, or non-standard implementations.
2. **Read data model specification:** Thoroughly review specs/001-gui-podcast-studio/data-model.md to understand complete 11-table structure including column definitions (UUIDs, JSONB columns, enums), foreign key relationships and cascading delete rules, Row-Level Security policy requirements for tenant isolation, indexes (tenant_id, JSONB GIN, expression indexes), triggers (update_updated_at function), constraints (CHECK constraints, UNIQUE constraints), and pgcrypto encryption functions for sensitive credentials.
3. **Inspect deployed database:** Connect to deployed PostgreSQL instance using credentials from .env configuration, execute SQL queries to list all tables (`\dt` or information_schema.tables), for each table query column definitions including data types and nullability (`\d+ table_name`), list all indexes including GIN and expression indexes (`\di`), inspect constraints including foreign keys and check constraints, verify RLS policy existence (`\d+ table_name` RLS section), check for triggers and custom functions (updated_at, encryption functions).
4. **Compare schema to specification:** Create systematic comparison matrix mapping spec requirements to deployed reality for each of 11 tables, identify missing tables entirely (critical blocker), identify existing tables with missing columns (schema drift), identify missing indexes especially tenant_id and JSONB GIN indexes (performance impact), verify RLS policies enabled and correctly configured for tenant isolation (security critical), check triggers for automated timestamp updates, validate constraint enforcement (data integrity), document any extra/unexpected schema elements not in specification.
5. **Create migration strategy:** Assess if Alembic migration directory exists (apps/api/alembic/) and contains migration files, evaluate migration history table (alembic_version) to understand applied migrations, determine if incremental migrations can address gaps or if fresh reset simpler given Context Synthesis acceptance, for fresh reset approach: plan to drop all tables and recreate from scratch using Alembic, for incremental approach: outline specific migrations needed to reach spec compliance, document risks/benefits of each approach considering development velocity vs production continuity.
6. **User confirmation:** If comparison reveals major discrepancies (>3 missing tables, critical RLS policy gaps, or fundamental schema misalignment), present findings to User with migration strategy recommendation, confirm database reset approach leveraging pre-approval from Context Synthesis for fresh migrations, document User's confirmed approach for execution in Phase 2 Task 2.2 (Alembic Migration Setup), proceed only after explicit approval to avoid destructive database operations without consent.

### Task 1.3 – Testing Infrastructure Setup │ Agent_Assessment_Foundation ✅ COMPLETED

- **Objective:** Establish comprehensive testing infrastructure for TDD approach with >80% coverage requirement, configuring pytest (backend), Jest (frontend), and Playwright (E2E) testing frameworks with coverage reporting and CI/CD integration to enforce 100% pass rate before deployment.
- **Output:** Complete testing infrastructure delivering: (1) backend pytest configuration (pytest.ini, test discovery, async support) with working sample test, (2) frontend Jest configuration (jest.config.js, React Testing Library integration) with working component test, (3) E2E Playwright configuration (playwright.config.ts, browser setup) with working health check test, (4) coverage reporting for all test suites configured with >80% thresholds and aggregated reports, (5) updated GitHub Actions workflow enforcing test execution and 100% pass rate gate before deployment with coverage artifacts.
- **Guidance:** Context Synthesis mandates TDD approach with >80% coverage and 100% pass rate before task progression. Testing infrastructure must support backend (Python/FastAPI), frontend (TypeScript/Next.js/React), and E2E workflows. Configuration should enable parallel test execution (pytest-xdist, Jest workers) for performance. Sample tests validate setup correctness and serve as templates for future test development. CI/CD integration ensures quality gates cannot be bypassed.
- **Beads Issue:** podcaststudiohub-xo0 | **Status:** Closed | **Completion Date:** 2025-11-11
- **Key Findings:** All testing frameworks operational with >80% coverage thresholds, sample tests passing, CI/CD integration complete

1. **Configure backend testing:** Install testing dependencies via uv: pytest (test runner), pytest-asyncio (async test support for FastAPI), pytest-cov (coverage reporting), httpx (async HTTP client for API testing); create pytest.ini in apps/api/ configuring test discovery patterns (tests/ directory, test_*.py files), async mode settings, coverage paths; write sample API test in tests/test_health.py validating health check endpoint responds correctly, verifying pytest runs successfully with coverage reporting.
2. **Configure frontend testing:** Install frontend testing dependencies via npm in apps/web/: Jest (test runner), @testing-library/react (React component testing), @testing-library/jest-dom (DOM matchers), @testing-library/user-event (user interaction simulation); create jest.config.js with Next.js preset configuration, module path mapping for TypeScript imports, coverage collection settings; write sample component test in __tests__/components/Button.test.tsx verifying basic component rendering and interaction, confirm Jest executes with coverage output.
3. **Configure E2E testing:** Install Playwright via npm in apps/web/: @playwright/test package; create playwright.config.ts configuring browser targets (Chromium, Firefox, WebKit), base URL (http://localhost:3000 for local, dev.podcaststudiohub.me for staging), test directory structure, screenshot/video capture on failure, parallel execution workers; write sample E2E test in e2e/health.spec.ts navigating to health check endpoint and asserting successful response, verify Playwright runs across configured browsers.
4. **Configure coverage reporting:** Set up pytest-cov for backend with >80% coverage threshold in pytest.ini, configure coverage paths to include apps/api/src/ excluding tests and migrations, enable HTML and terminal coverage reports; configure Jest coverage for frontend with >80% threshold in jest.config.js, include apps/web/src/ excluding test files and configuration, enable LCOV and HTML reporters; create coverage aggregation script combining backend and frontend reports for holistic project coverage view.
5. **Integrate tests into CI/CD:** Update GitHub Actions workflow (.github/workflows/deploy.yml or create test.yml) to execute all test suites on push/PR events, add backend test job running pytest with coverage in apps/api/, add frontend test job running Jest with coverage in apps/web/, add E2E test job running Playwright against deployed staging environment, enforce 100% pass rate requirement (fail build if any test fails), generate coverage reports as GitHub Actions artifacts for review, configure coverage badges in README if desired.

### Task 1.4 – Environment Configuration Validation │ Agent_Assessment_Foundation ✅ COMPLETED

- **Objective:** Validate all required environment variables and API credentials are properly configured across development, staging, and production environments, test credential functionality for external services (Gemini, OpenAI, ElevenLabs, S3, Transistor.fm), and document validated configuration with identified gaps requiring User-provided credentials.
- **Output:** Environment configuration validation report including: (1) .env file inventory confirming existence across root, apps/web/, and apps/api/ with completeness assessment against .env.example template, (2) credential verification results for all API services with working/missing/invalid status per credential, (3) documented User coordination for missing API keys (particularly Transistor.fm which is new scope), (4) final validated configuration documentation confirming all services accessible and ready for development use.
- **Guidance:** Depends on: Task 1.1 Output (smoke test identifies which API integrations are attempted in current deployment). Context Synthesis confirms API keys exist for Gemini, OpenAI, ElevenLabs in current .env but Transistor.fm API key likely needs addition. Environment variables include: DATABASE_URL, REDIS_URL, ENCRYPTION_KEY, JWT_SECRET_KEY, API keys for external services, AWS credentials for S3. Validation must test actual API connectivity, not just environment variable existence.
- **Beads Issue:** podcaststudiohub-wxr | **Status:** Closed | **Completion Date:** 2025-11-11
- **Key Findings:** 5/7 services working (71% readiness), created automated test script, missing AWS S3 and Transistor.fm credentials documented

1. **Verify .env files exist:** Check for .env file in project root directory, verify apps/web/.env.local exists for Next.js frontend environment variables, confirm apps/api/.env exists for backend API configuration, compare each .env file against corresponding .env.example template to identify missing environment variables, document completeness status (all required vars present vs gaps identified), note any sensitive credentials missing that require secure User provision.
2. **Test API credentials:** Write simple test scripts (apps/api/scripts/test_credentials.py) to verify external service connectivity: test Gemini API key by making simple generation request to validate authentication and quota, test OpenAI API key with basic completion or TTS request, test ElevenLabs API key by retrieving available voices or making minimal TTS request, test S3 connectivity by attempting bucket listing or test file upload with AWS access/secret keys, document test results per service (working/invalid/missing/quota exceeded).
3. **User coordination:** Based on credential testing results, compile list of missing or invalid API keys requiring User provision, particularly request Transistor.fm API key (new scope per Context Synthesis) with guidance on obtaining from developers.transistor.fm account, provide secure method for User to supply credentials (avoid plaintext chat, use secure file sharing or direct .env editing guidance), add provided credentials to appropriate .env files in correct format, update .env.example with any new variable templates for future reference.
4. **Final validation:** Re-run credential test scripts after User provides missing keys to confirm all services now accessible, execute comprehensive connectivity test covering all external dependencies (database, Redis, all API services, S3 storage), verify no authentication errors, rate limiting issues, or quota problems that would block development, compile final validated configuration documentation listing: all working credentials, confirmed service accessibility status, any remaining limitations or warnings (e.g., API quota considerations), approved configuration ready for Phase 2 implementation work.

## Phase 2: Core Backend Infrastructure

### Task 2.1 – Database Models for Core Entities │ Agent_Backend_Core

- Create base model mixin (apps/api/src/models/base.py) with common fields: id (UUID), tenant_id (UUID), created_at, updated_at; implement __tablename__ conventions
- Implement users model (apps/api/src/models/user.py) matching data-model.md: authentication fields (email, password_hash), encrypted_api_keys JSONB column, is_active/is_verified flags, email validation constraint
- Implement projects model (apps/api/src/models/project.py): foreign key to users, podcast_metadata JSONB, default_tts_config_id and default_template_id (nullable, deferred to Phase 4), is_archived flag
- Implement episodes and content_sources models (apps/api/src/models/episode.py, content_source.py): episodes with metadata JSONB, generation_status enum, distribution_status JSONB; content_sources with source_type enum, source_data JSONB, extraction_status; define cascading deletes

### Task 2.2 – Alembic Migration System Setup │ Agent_Backend_Core

- **Guidance:** Depends on: Task 2.1 Output

1. Install and initialize Alembic - install alembic via uv, run `alembic init alembic` in apps/api/, configure alembic.ini with DATABASE_URL from environment
2. Configure Alembic environment - edit alembic/env.py to import SQLAlchemy models, configure target_metadata for auto-detection, set up async database connection
3. Generate initial migration - run `alembic revision --autogenerate -m "Initial core entities"` to create migration for users, projects, episodes, content_sources tables
4. Add RLS policies to migration - edit generated migration file to add PostgreSQL Row-Level Security policies from data-model.md: ALTER TABLE ... ENABLE ROW LEVEL SECURITY; CREATE POLICY tenant_isolation_...
5. Test migration - run `alembic upgrade head` against fresh PostgreSQL database, verify all tables created with correct schema, indexes, constraints, and RLS policies

### Task 2.3 – Authentication System Implementation │ Agent_Backend_Core

- **Guidance:** Depends on: Task 2.2 Output

1. Create authentication schemas - define Pydantic schemas (apps/api/src/schemas/auth.py): UserRegister, UserLogin, UserResponse, TokenResponse with email/password validation
2. Implement authentication service - create auth_service.py with functions: hash_password (bcrypt), verify_password, create_jwt_token (RS256), verify_jwt_token; handle user creation and credential verification
3. Implement registration endpoint - create /auth/register POST route in auth.py router, validate email uniqueness, hash password, create user in database, return UserResponse
4. Implement login endpoint - create /auth/login POST route, verify credentials, generate JWT access token with user claims (user_id, tenant_id, email), return TokenResponse with token
5. Implement JWT middleware - create middleware (apps/api/src/middleware/auth.py) to extract Bearer token from headers, verify token, inject user context into request state for protected routes
6. Write authentication tests - create test_auth.py with pytest tests: successful registration, duplicate email rejection, successful login, invalid credentials rejection, JWT token validation, middleware protection; achieve >80% coverage

### Task 2.4 – Multi-Tenant Middleware Setup │ Agent_Backend_Core

- **Guidance:** Depends on: Task 2.3 Output

1. Create tenant middleware - implement middleware to extract tenant_id from JWT claims (injected by Task 2.3 auth middleware), validate tenant_id exists, inject into request state
2. Configure database session for RLS - modify database session factory (apps/api/src/dependencies.py) to execute `SET LOCAL app.tenant_id = '<tenant_id>'` for each request using tenant from middleware
3. Implement tenant dependency injection - create FastAPI dependency `get_current_tenant()` that extracts tenant_id from request state, use in route parameters for tenant-aware operations
4. Write tenant isolation tests - create test_tenant_isolation.py: create two tenants with separate data, verify user from tenant A cannot query/modify tenant B data, confirm RLS policies enforce boundaries; achieve >80% coverage for critical security path

### Task 2.5 – Project Management API │ Agent_Backend_Core

- **Guidance:** Depends on: Task 2.4 Output

- Create project schemas (apps/api/src/schemas/project.py) - ProjectCreate, ProjectUpdate, ProjectResponse with podcast_metadata JSONB validation (show_title, author, description required), name length constraints per data-model.md
- Implement project service (apps/api/src/services/project_service.py) - create_project, get_projects (tenant-scoped list with pagination), get_project_by_id, update_project, archive_project (soft delete via is_archived flag); enforce tenant isolation
- Create project routes (apps/api/src/routers/projects.py) - POST /projects (create), GET /projects (list with filters), GET /projects/{id} (detail), PUT /projects/{id} (update), DELETE /projects/{id} (archive); apply JWT authentication and tenant middleware dependencies
- Write project tests (tests/test_projects.py) - test all CRUD operations, verify tenant isolation (cannot access other tenant's projects), test validation errors (missing required metadata, invalid name length), test pagination; achieve >80% coverage

### Task 2.6 – Episode Management API │ Agent_Backend_Core

- **Guidance:** Depends on: Task 2.5 Output

- Create episode schemas (apps/api/src/schemas/episode.py) - EpisodeCreate, EpisodeUpdate, EpisodeResponse with metadata JSONB (title required, episode_number, description, format enum), generation_status enum validation, distribution_status JSONB structure
- Implement episode service (apps/api/src/services/episode_service.py) - create_episode (validate project exists and belongs to tenant), get_episodes (scoped to project and tenant), get_episode_by_id, update_episode, delete_episode; manage generation_status transitions (draft → queued → processing → completed/failed)
- Create episode routes (apps/api/src/routers/episodes.py) - POST /projects/{project_id}/episodes (create), GET /projects/{project_id}/episodes (list), GET /episodes/{id} (detail), PUT /episodes/{id} (update), DELETE /episodes/{id} (delete); apply authentication, tenant middleware, project ownership validation
- Write episode tests (tests/test_episodes.py) - test CRUD operations, verify project relationship enforcement (cannot create episode for other tenant's project), test generation_status state transitions, test metadata validation; achieve >80% coverage

### Task 2.7 – Content Source Management API │ Agent_Backend_Core

- **Guidance:** Depends on: Task 2.6 Output

- Create content source schemas (apps/api/src/schemas/content.py) - ContentSourceCreate, ContentSourceResponse with source_type enum (url, pdf, text), source_data JSONB structure per type (URL: {url, title}, PDF: {filename, s3_key}, text: {content}), extraction_status enum
- Implement content service (apps/api/src/services/content_service.py) - add_content_source (validate episode exists and belongs to tenant, validate source_data structure matches source_type), get_content_sources (scoped to episode), delete_content_source; initialize extraction_status as 'pending'
- Create content routes (apps/api/src/routers/content.py) - POST /episodes/{episode_id}/content (add source), GET /episodes/{episode_id}/content (list sources), DELETE /content/{id} (remove source); apply authentication, tenant middleware, episode ownership validation
- Write content tests (tests/test_content.py) - test adding URL/PDF/text sources, verify episode relationship enforcement, test source_data validation for each type, test extraction_status initialization; achieve >80% coverage

## Phase 3: AI Script Generation & Quality Gates

### Task 3.1 – Content Extraction Service │ Agent_AI_ScriptGen

1. Ad-Hoc Delegation – Podcastfy content_parser integration research (optional: .claude/commands/apm-7-delegate-research.md to understand content_parser/ APIs and best integration approach)
2. Create content extraction service base - implement ContentExtractionService (apps/api/src/services/content_extraction_service.py) that imports podcastfy.content_parser modules, defines async wrapper methods
3. Implement URL extraction - wrap website_extractor.py functionality, call extract_content_from_url, handle 404/timeout errors, update content_sources.extracted_content and extraction_status
4. Implement PDF extraction - wrap pdf_extractor.py functionality, handle PDF file upload/storage, extract text content, update database with extracted content
5. Implement text content handling - for source_type='text', extract content directly from source_data.content field, validate non-empty, update extraction_status
6. Write extraction tests - create test_content_extraction.py: test URL extraction with mock responses, test PDF extraction with sample file, test error handling (invalid URL, corrupted PDF), verify extraction_status transitions; achieve >80% coverage

### Task 3.2 – Script Generation Service with Gemini │ Agent_AI_ScriptGen

- **Guidance:** Depends on: Task 3.1 Output

1. Create script generation service base - implement ScriptGenerationService (apps/api/src/services/script_generation_service.py) that imports podcastfy.content_generator, defines async wrapper for generate_podcast_transcript method
2. Configure Gemini API integration - wrap LiteLLM/Gemini API client from existing Podcastfy code, configure API key from environment, set generation parameters (temperature: 0.7, frequency_penalty: 0.75, presence_penalty: 0.75 per spec)
3. Implement generation logic - create generate_script method that accepts episode_id, retrieves extracted content from content_sources, calls Podcastfy generation with content and conversation format, returns XML-format transcript
4. Implement status management - update episodes.generation_status transitions: draft → queued (when generation starts), queued → processing (during generation), processing → completed (on success) or processing → failed (on error); store transcript in episodes.transcript column
5. Write generation tests - create test_script_generation.py: test generation with mocked Gemini responses, verify status transitions, test error handling (API failures, invalid content), verify transcript format validation; achieve >80% coverage

### Task 3.3 – Script Quality Metrics Calculator │ Agent_AI_ScriptGen

- **Guidance:** Depends on: Task 3.2 Output

- Create quality metrics infrastructure - implement QualityMetricsCalculator (apps/api/src/services/quality_metrics_service.py) that parses XML transcript to extract Person1/Person2 dialogue, defines metric calculation interface, stores results in episodes.generation_progress.quality_metrics JSONB
- Implement core metrics - calculate length (total words, duration estimate at 150 words/min), coherence score (sentence length variation, topic keyword consistency), tone detection (keyword matching: casual vs academic vs humorous vocabulary patterns)
- Implement speaker metrics - calculate speaker balance (Person1 word count / Person2 word count ratio, flag if >70/30 imbalance), banter detection (count dialogue turns, flag if >200 words without turn-taking)
- Write quality metrics tests - create test_quality_metrics.py: test each metric with sample transcripts (good balance, poor balance, monotone, engaging banter), verify threshold detection, test JSONB storage format; achieve >80% coverage

### Task 3.4 – AI Pre-Screening Service │ Agent_AI_ScriptGen

- **Guidance:** Depends on: Task 3.3 Output

1. Define pre-screening thresholds - create configuration (apps/api/src/config.py or database) for quality thresholds: min_length (100 words), min_coherence (0.5 score), max_speaker_imbalance (70/30 ratio), max_monologue_length (200 words without turn)
2. Implement evaluation engine - create PreScreeningService (apps/api/src/services/pre_screening_service.py) that calls QualityMetricsCalculator, evaluates each metric against thresholds, aggregates pass/fail decision with specific failure reasons
3. Update episode status with results - store pre_screen_status in episodes.generation_progress JSONB: {status: 'passed'/'failed', timestamp, failed_metrics: ['speaker_imbalance', 'low_coherence'], quality_scores: {...}}; prevent episodes from reaching human review if failed
4. Write pre-screening tests - create test_pre_screening.py: test passing scripts (all thresholds met), test each failure condition (too short, poor coherence, imbalanced speakers, excessive monologue), test edge cases (borderline thresholds), verify status updates; achieve >80% coverage

### Task 3.5 – Human Review Workflow API │ Agent_AI_ScriptGen

- **Guidance:** Depends on: Task 3.4 Output

- Create review schemas (apps/api/src/schemas/review.py) - ReviewRequest with status enum (approved/rejected), feedback text, ScriptReviewResponse with script content and quality metrics from pre-screening
- Implement review service (apps/api/src/services/review_service.py) - get_pending_reviews (episodes with pre_screen_status='passed' and review_status='pending'), approve_script (mark ready for audio generation), reject_script (store feedback, allow regeneration), manual_override (approve despite pre-screening failure with justification)
- Create review routes (apps/api/src/routers/review.py) - GET /reviews/pending (list scripts awaiting review with quality scores), PUT /reviews/{episode_id}/approve, PUT /reviews/{episode_id}/reject with feedback; apply authentication and tenant middleware
- Write review workflow tests (tests/test_review.py) - test retrieving pending reviews, test approval workflow progression, test rejection with regeneration trigger, test manual override cases, verify status transitions; achieve >80% coverage

### Task 3.6 – Conversation Template System │ Agent_AI_ScriptGen

- **Guidance:** Depends on: Task 3.2 Output

1. Create conversation_templates model and migration - implement conversation_templates SQLAlchemy model from data-model.md (name, config JSONB with format/speakers/conversation_style), create Alembic migration, add indexes and RLS policies
2. Implement template CRUD API - create template router, schemas, service following Phase 2 patterns (apps/api/src/routers/templates.py, schemas/template.py, services/template_service.py); support create/read/update/delete templates with tenant scoping
3. Create preset templates - seed database with 3 conversation presets: casual (friendly tone, moderate pacing), academic (formal tone, detailed explanations), humorous (lighthearted tone, witty exchanges); define speaker personalities per preset
4. Integrate templates with script generation - modify ScriptGenerationService from Task 3.2 to accept template_id parameter, load template config, pass conversation_style to Podcastfy generation, apply speaker personality prompts
5. Write template tests - create test_templates.py: test CRUD operations, verify preset templates exist, test template application to generation (mock generation with template config), verify tenant isolation; achieve >80% coverage

## Phase 4: Audio Production Pipeline

### Task 4.1 – TTS Configuration Management API │ Agent_Audio_Production

- Create tts_configurations model and migration - implement from data-model.md (provider enum, config JSONB with voice_settings and speaker_assignments), create Alembic migration with indexes/RLS
- Implement TTS config CRUD API - create router/schemas/service (apps/api/src/routers/tts_configs.py, schemas/tts_config.py, services/tts_config_service.py) for managing TTS configurations with tenant scoping
- Create default ElevenLabs configurations - seed database with default config using user's ElevenLabs voice (host) + configurable co-host voices per show; support OpenAI/Edge TTS alternatives
- Write TTS config tests - test CRUD operations, verify voice settings validation, test tenant isolation; achieve >80% coverage

### Task 4.2 – ElevenLabs TTS Integration Service │ Agent_Audio_Production

- **Guidance:** Depends on: Task 4.1 Output

1. Wrap existing Podcastfy TTS - create TTSService (apps/api/src/services/tts_service.py) that wraps podcastfy/text_to_speech.py and podcastfy/tts/providers/elevenlabs.py functionality
2. Implement ElevenLabs voice assignment - load tts_configuration for episode, extract speaker_assignments (Person1 → user voice, Person2 → co-host voice), map to ElevenLabs voice IDs
3. Generate audio from approved script - accept approved transcript from Phase 3, split by speaker tags, call ElevenLabs API for each speaker segment, merge audio chunks using PyDub
4. Store generated audio - save audio file to local filesystem (data/audio/), update episodes.audio_file_path, update generation_status to 'completed'
5. Write TTS integration tests - test voice assignment mapping, test audio generation with mocked ElevenLabs API, verify audio merging, test error handling; achieve >80% coverage

### Task 4.3 – Audio Snippet Management System │ Agent_Audio_Production

1. Create audio_snippets model and migration - implement from data-model.md (snippet_type enum, file_path, s3_key, duration/format metadata), create Alembic migration with indexes/RLS
2. Implement snippet upload API - create POST /snippets endpoint to upload intro/outro/midroll audio files, extract metadata (duration, format, sample_rate) using PyDub, store file locally and S3
3. Implement snippet CRUD API - create GET /snippets (list with filtering by type), GET /snippets/{id} (detail), DELETE /snippets/{id}; support project-level and user-level snippets
4. Implement metadata extraction - use PyDub to analyze uploaded audio: extract duration_seconds, file_format, sample_rate, bit_rate, channels; store in audio_snippets table
5. Write snippet management tests - test audio upload with various formats (mp3, wav), verify metadata extraction accuracy, test S3 storage, test CRUD operations; achieve >80% coverage

### Task 4.4 – Episode Layout Template System │ Agent_Audio_Production

- **Guidance:** Depends on: Task 4.3 Output

1. Create episode_layouts model and migration - implement from data-model.md (layout_config JSONB defining segment positions), create Alembic migration with indexes/RLS
2. Implement layout CRUD API - create router/schemas/service for managing composition layouts (apps/api/src/routers/layouts.py, schemas/layout.py, services/layout_service.py)
3. Create default layout templates - seed database with templates: "Standard" (intro → content → outro), "WithMidroll" (intro → content → midroll@50% → outro), "MinimalIntro" (intro → content)
4. Write layout tests - test CRUD operations, verify layout_config structure validation (segment ordering, position formats), test tenant isolation; achieve >80% coverage

### Task 4.5 – Audio Composition Engine │ Agent_Audio_Production

- **Guidance:** Depends on: Task 4.2 Output by Agent_Audio_Production and Task 4.4 Output

1. Create episode_compositions model and migration - implement from data-model.md (timeline JSONB, composition_status enum), create Alembic migration
2. Implement composition service - create CompositionService (apps/api/src/services/composition_service.py) that loads layout template, retrieves snippet files, merges with generated podcast audio using PyDub
3. Implement audio normalization - use PyDub to normalize audio levels across snippets and main content, apply crossfade between segments per layout configuration, ensure consistent output quality
4. Generate composition timeline - create timeline JSONB tracking segment positions: [{segment_type, snippet_id, start_time, end_time, duration, audio_source}], store in episode_compositions table
5. Write composition tests - test audio merging with sample snippets, verify normalization accuracy, test timeline generation, test error handling (missing snippets); achieve >80% coverage

### Task 4.6 – Complete Audio Generation Orchestration │ Agent_Audio_Production

- **Guidance:** Depends on: Task 4.5 Output

- Implement end-to-end orchestration service - create AudioOrchestrationService that coordinates: retrieve approved script → generate TTS audio (Task 4.2) → apply composition layout (Task 4.5) → save final audio
- Implement Celery background task - create podcast_generation Celery task (apps/api/src/tasks/podcast_generation.py) for async audio generation, update episodes.generation_progress with real-time status
- Implement progress tracking API - create GET /episodes/{id}/progress endpoint with Server-Sent Events (SSE) to stream generation progress to frontend (extraction → script → audio → composition stages)
- Write orchestration tests - test complete pipeline with mocked components, verify Celery task execution, test progress updates, test error recovery; achieve >80% coverage

## Phase 5: Publishing & External Integrations

### Task 5.1 – S3 Storage Service │ Agent_External_Integrations

1. Ad-Hoc Delegation – AWS S3 SDK integration best practices (optional: .claude/commands/apm-7-delegate-research.md)
2. Implement S3 service - create S3StorageService (apps/api/src/services/s3_service.py) using boto3, implement upload_audio, upload_snippet, generate_presigned_url methods
3. Configure S3 bucket structure - organize uploads: s3://bucket/podcasts/{project_id}/episodes/{episode_id}.mp3, s3://bucket/snippets/{user_id}/{snippet_id}.mp3
4. Implement backup workflow - after audio composition complete (Phase 4), upload final audio to S3, update episodes.audio_s3_key and audio_s3_url
5. Write S3 integration tests - test upload operations, verify bucket structure, test presigned URL generation, test error handling (invalid credentials); achieve >80% coverage

### Task 5.2 – Transistor.fm API Integration │ Agent_External_Integrations

- **Guidance:** Depends on: Task 5.1 Output

1. Ad-Hoc Delegation – Transistor.fm API capabilities research (use developers.transistor.fm documentation to understand show creation, episode upload, metadata management APIs)
2. Create Transistor service - implement TransistorService (apps/api/src/services/transistor_service.py) with API client using httpx, authenticate with API key from .env
3. Implement show creation - create create_show method that calls Transistor API to create new podcast show with metadata (title, description, artwork), store show ID in projects.podcast_metadata.transistor_show_id
4. Implement episode upload - create upload_episode method that uploads audio file URL (S3 URL from Task 5.1), episode metadata (title, description, publication_date), returns Transistor episode ID
5. Implement metadata sync - create update_episode_metadata method to sync changes from database to Transistor platform
6. Write Transistor integration tests - test show creation with mocked API, test episode upload workflow, verify metadata synchronization, test error handling (API failures, rate limits); achieve >80% coverage

### Task 5.3 – RSS Feed Generation Service │ Agent_External_Integrations

- **Guidance:** Depends on: Task 5.2 Output

1. Create rss_feeds model and migration - implement from data-model.md (s3_key, public_url, validation_status JSONB), create Alembic migration
2. Implement RSS generator - create RSSService (apps/api/src/services/rss_service.py) that generates RSS 2.0 XML with all podcast metadata from projects and published episodes
3. Implement RSS validation - validate generated feed against Apple Podcasts/Spotify requirements: required tags, artwork dimensions (1400x1400 min), episode enclosure URLs
4. Upload RSS to S3 - save generated RSS feed to S3 (s3://bucket/feeds/{project_id}/feed.xml), update rss_feeds table with public_url
5. Write RSS generation tests - test RSS XML structure, verify Apple/Spotify compliance, test validation rules, test S3 upload; achieve >80% coverage

### Task 5.4 – Show Setup Workflow API │ Agent_External_Integrations

- **Guidance:** Depends on: Task 5.2 Output

- Implement show creation orchestration - create ShowSetupService that coordinates: create project in database → create Transistor show (Task 5.2) → upload artwork to S3 → generate initial RSS feed (Task 5.3)
- Create show setup API endpoint - POST /shows endpoint that accepts show metadata (title, description, artwork, voice configuration), orchestrates setup workflow, returns complete show configuration
- Implement show status tracking - track setup progress in projects.podcast_metadata: {setup_status: 'pending'/'transistor_created'/'artwork_uploaded'/'rss_generated'/'complete'}
- Write show setup tests - test complete workflow, verify Transistor integration, test partial failure recovery, test status tracking; achieve >80% coverage

### Task 5.5 – Publishing Orchestration Service │ Agent_External_Integrations

- **Guidance:** Depends on: Task 5.3 Output and Task 4.6 Output by Agent_Audio_Production

1. Implement publishing service - create PublishingService that orchestrates: upload audio to S3 (Task 5.1) → upload to Transistor (Task 5.2) → regenerate RSS feed (Task 5.3) → update distribution_status
2. Create publishing API endpoint - POST /episodes/{id}/publish that triggers publishing workflow, returns publishing status with progress tracking
3. Implement manual vs auto-publish toggle - add auto_publish flag to projects, support manual trigger (MVP) with future auto-publish capability
4. Write publishing tests - test complete publishing pipeline, verify status updates in episodes.distribution_status JSONB, test error handling; achieve >80% coverage

## Phase 6: Frontend User Experience

### Task 6.1 – Authentication & Layout Components │ Agent_Frontend

1. Implement authentication pages - create login/signup pages (apps/web/src/app/(auth)/login, signup) using NextAuth.js, connect to backend /auth/register and /auth/login endpoints
2. Create layout components - implement main layout with navigation (apps/web/src/components/layout/), sidebar for show selection, header with user menu
3. Implement dashboard page - create dashboard (apps/web/src/app/(auth)/dashboard/) showing overview: pending reviews count, recent episodes, show statistics
4. Write authentication tests - create auth flow E2E tests with Playwright, verify login/logout, test JWT token handling; achieve >80% coverage

### Task 6.2 – Show Management UI │ Agent_Frontend

- **Guidance:** Depends on: Task 6.1 Output

- Create show list page - implement projects list (apps/web/src/app/(auth)/projects/) with create new show button, show cards displaying metadata
- Implement show creation wizard - multi-step form for show setup: basic info (title, description) → voice configuration (host/co-host voices) → meta assets (intro/outro upload) → Transistor integration
- Create show detail page - display show metadata, episode list, voice configuration, snippet library, publishing status
- Write show management tests - test show CRUD operations, verify wizard workflow, test voice configuration UI; achieve >80% coverage

### Task 6.3 – Episode Creation & Management UI │ Agent_Frontend

- **Guidance:** Depends on: Task 6.2 Output

1. Create episode list page - implement episodes list for selected show (apps/web/src/app/(auth)/episodes/) with filters (status, publication date), create episode button
2. Implement episode creation form - multi-step workflow: add content sources (URLs/PDF upload) → select conversation template → trigger generation → monitor progress
3. Create episode detail page - display episode metadata, content sources, generated transcript, quality scores, audio player for preview
4. Implement real-time progress tracking - connect to SSE endpoint from Phase 4 Task 4.6, display progress bar showing extraction → script → audio → composition stages
5. Write episode management tests - test episode creation workflow, verify progress tracking UI, test content source management; achieve >80% coverage

### Task 6.4 – Script Review UI │ Agent_Frontend

- **Guidance:** Depends on: Task 6.3 Output

- Create review queue page - implement pending reviews list (apps/web/src/app/(auth)/reviews/) showing episodes awaiting human review with quality scores from pre-screening
- Implement review interface - display generated transcript with quality metrics (speaker balance, coherence score), approve/reject buttons with feedback textarea
- Implement manual override UI - for pre-screening failures, show failure reasons, allow manual approval with justification field
- Write review UI tests - test review workflow, verify quality metrics display, test approval/rejection flows; achieve >80% coverage

### Task 6.5 – Audio Asset Management UI │ Agent_Frontend

- **Guidance:** Depends on: Task 6.2 Output

- Create snippet library page - display user's audio snippets (intros/outros/midrolls) with upload interface, preview player, metadata display (duration, format)
- Implement snippet upload - drag-and-drop or file picker for audio upload, connect to backend POST /snippets endpoint, display upload progress
- Implement layout template selector - UI for selecting composition layout when creating episode, preview layout structure (segment visualization)
- Write asset management tests - test snippet upload workflow, verify audio preview, test layout selection; achieve >80% coverage

### Task 6.6 – Publishing & Settings UI │ Agent_Frontend

- **Guidance:** Depends on: Task 6.5 Output and Task 5.5 Output by Agent_External_Integrations

- Create publishing interface - implement publish button on episode detail page, display publishing progress (S3 upload → Transistor upload → RSS regeneration), show distribution status
- Implement settings page - user profile settings, API credentials management (encrypted display), show-level settings (auto-publish toggle, default voice configuration)
- Create Transistor.fm integration panel - display connected shows, show Transistor episode IDs, provide manual sync button
- Write publishing UI tests - test publish workflow, verify status tracking, test settings management; achieve >80% coverage

## Phase 7: Quality Assurance & Testing

### Task 7.1 – Backend Integration Test Suite │ Agent_QA_Testing

- Create comprehensive API integration tests - test complete workflows: user registration → show creation → episode generation → script review → audio production → publishing; verify database state at each step
- Implement database transaction tests - verify RLS policies enforce tenant isolation across all tables, test cascading deletes, test constraint enforcement
- Create error scenario tests - test API error handling, database connection failures, external API failures (Gemini, ElevenLabs, Transistor), verify graceful degradation
- Achieve >80% backend coverage - run pytest-cov, identify untested code paths, add missing tests to reach coverage threshold

### Task 7.2 – Frontend E2E Test Suite │ Agent_QA_Testing

- **Guidance:** Depends on: Task 6.6 Output by Agent_Frontend

- Create comprehensive E2E workflows - implement Playwright tests for complete user journeys: signup → create show → add episode → review script → publish episode
- Test cross-browser compatibility - run E2E tests on Chrome, Firefox, Safari; verify responsive design on desktop/tablet breakpoints
- Implement accessibility tests - verify ARIA labels, keyboard navigation, screen reader compatibility
- Achieve >80% frontend coverage - run Jest coverage report, add missing component/integration tests

### Task 7.3 – Performance & Load Testing │ Agent_QA_Testing

- Implement API performance tests - measure response times for all endpoints, verify <200ms for metadata operations, <2s for content extraction initiation per spec
- Create concurrent generation tests - test 10-20 simultaneous podcast generation jobs, verify Celery worker handling, monitor resource usage on staging VPS (8 vCPU/16GB RAM)
- Test production constraints - verify application runs on production VPS specs (2 CPU/4GB RAM), identify resource bottlenecks, optimize if needed
- Database query optimization - verify <100ms for episode library queries with 1000+ episodes per user, optimize slow queries with EXPLAIN ANALYZE

### Task 7.4 – CI/CD Pipeline Validation │ Agent_QA_Testing

- **Guidance:** Depends on: Task 7.2 Output

- Update GitHub Actions workflow - configure test execution for backend (pytest), frontend (Jest), E2E (Playwright), enforce 100% pass rate before merge
- Implement coverage reporting - generate coverage badges, upload reports as artifacts, enforce >80% threshold
- Configure deployment validation - add smoke tests to CI/CD, verify deployment health checks pass on staging before production promotion
- Write CI/CD documentation - document test execution process, coverage requirements, deployment procedures in developer docs

