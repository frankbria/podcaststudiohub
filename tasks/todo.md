# Issue #225 — docs: rewrite CLAUDE.md/README for the SaaS monorepo; fix refs, auth, JWT drift; remove cruft & IP

Plan source: issue body (acceptance criteria). Verified against current repo 2026-06-22.

## Steps

1. **Rewrite `CLAUDE.md` for the monorepo**
   - Describe PodcastStudioHub SaaS monorepo: `apps/api` (FastAPI + Celery + Postgres + Alembic + JWT auth), `apps/web` (Next.js), `deployment/`.
   - Add a scoped **Upstream Podcastfy Engine** subsection for the root `podcastfy/` package (keep useful engine details, clearly scoped).
   - Fix dev commands to target the monorepo, not the upstream engine.

2. **Fix `README.md` dead refs + auth wording**
   - `requirements.txt` (line 110) → drop pip line, `uv sync` only.
   - `docker-compose.yml` (tree line 291) → remove.
   - `deployment/QUICKSTART.md` & `DEPLOYMENT.md` (tree 274-275) → `deployment/README.md`.
   - `UPSTREAM_SYNC.md` (420/423) → remove dead refs, inline the note.
   - Auth: lines 13 & 70 "session-based" / "session management" → JWT-based.

3. **Fix JWT_ALGORITHM drift** — root `.env.example:17` `RS256` → `HS256` (matches `apps/api/src/config.py:33`). Keep file.

4. **Replace hardcoded IP `47.88.89.175`** with `<SERVER_IP>` placeholder:
   - `README.md` (1), `deployment/README.md` (30), `.github/DEPLOYMENT_SETUP.md` (4).

5. **Remove dev cruft** (git rm tracked):
   - `smoke-test-report-2025-11-11.md`, `schema-comparison-report-2025-11-11.md`, `coverage/combined-coverage-report.md`
   - `TESTING_AUTOMATION_ANALYSIS.md`, `TESTING_GUIDE.md`, `TESTING_GUIDE_MANUAL.md`
   - `apps/api/check_indexes.py`, `apps/api/verify_schema.py`, `apps/api/test_basic_operations.py`
   - `apps/api/.apm/` (stray placeholder — 2 files)
   - rm gitignored working-tree `demo.md` (root, apps/web, apps/api)

6. **gitignore runtime output dirs** — add `coverage/`, `test-results/`, `playwright-report/`, `/data/` to `.gitignore`.
   - `__pycache__/` already ignored; rm stale working dirs locally (no repo change).

## Acceptance criteria
- [ ] CLAUDE.md describes monorepo + scoped upstream-engine subsection
- [ ] README dead refs fixed; auth described as JWT
- [ ] root .env.example HS256
- [ ] hardcoded IP replaced everywhere
- [ ] dated reports, demo.md, apps/api scratch scripts deleted
- [ ] coverage/, data/, test-results/, playwright-report/ gitignored
- [ ] empty .apm placeholder deleted; stale __pycache__ handled

## Deviations / notes
- `TESTING_*.md`: issue groups as cruft; stale Nov-2025 guides → delete per issue.
- Root `.env.example` kept & fixed (not deleted) — only full-stack example with Postgres/Redis/NextAuth vars.
- `data/` has committed upstream sample mp3s; gitignore prevents new runtime data only, won't untrack samples.
- `__pycache__` already gitignored — no repo change needed.
- Root `.apm/` left intact; only stray `apps/api/.apm/` removed.
- Docs-drift root cause (m13v comment) → out of scope of acceptance criteria; noted as Known Limitation, no regen/CI guard built (YAGNI).
