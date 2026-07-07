# Issue #303 — Coverage gates are hollow (P2.5)

**Branch**: fix/303-coverage-gates (from main). **PR**: TBD.
(Previous entry: #302 tail complete, PR #344 merged 2026-07-05.)

## Problem
- Backend: `--cov-fail-under=0` in `apps/api/pytest.ini:21`, `.github/workflows/test.yml:84`, `.github/workflows/deploy-dev.yml:94` — gate enforces nothing.
- Frontend: `jest.config.js:35` excludes all of `src/app/**` — every page + the token-injecting proxy route sit outside the 80% threshold.

## Measured baseline (2026-07-06)
- Frontend with src/app included: 63.85% stmts / 54.48% branch / 54.64% funcs / 65.32% lines (gate = 80 on all four).
  - Zero coverage: projects/[id]/page.tsx (130 st), login/page.tsx (26 st), root page.tsx (12 st), nextauth route (5 st), layouts (12 st).
  - Partial: dashboard 50/103 st, episodes 120/247 st. Proxy route already 89/97%.
- Backend TOTAL: **81.96%** (6237 st, 1125 missed; 1587 passed, 1 known local-env failure test_audio_snippets::test_download_url_no_s3_config, 7 skipped). Need ~190 more covered statements for 85 + margin. Lowest: content router 40%, billing_service 41%, team_service 41%, episodes router 45%, rss_feed 48%, quality_metrics 55%, distribution_target_service 56%.

## Plan
1. **Frontend config** (`apps/web/jest.config.js`): drop `!src/app/**`; add boilerplate-only exclusions `!src/app/**/layout.tsx` (no loading/error/not-found files exist). Keep all page.tsx/route.ts under coverage.
2. **Frontend backfill** (TDD, model on existing __tests__/app/* suites):
   - New: `__tests__/app/login/page.test.tsx` (model: signup test)
   - New: `__tests__/app/projects/[id]/page.test.tsx` (model: episodes test)
   - New: `__tests__/app/page.test.tsx` (root redirect page)
   - New: `__tests__/app/api/auth/nextauth-route.test.ts` (mock next-auth, assert GET/POST exports)
   - Strengthen: dashboard page test (uncovered: 84,91-119,124-157,162-183,196-208,220-333), episodes page test (uncovered ranges incl. 204-285, 290-322, 618-665, 772-871)
   - Target: ≥80% on all four global metrics with src/app included.
3. **Backend gate**: set `--cov-fail-under` in pytest.ini + test.yml + deploy-dev.yml to measured target (≥85 per AC if reachable; else backfill to reach it — scope TBD from measurement).
4. **Backend backfill** (if measured <85): add tests for lowest-covered modules until ≥85.
5. Quality gate: full local test runs, lint, third-party review (opencode/GLM pre-PR + post-PR), deslop.
6. PR → demo (coverage gate demonstrably fails when coverage drops / passes at threshold) → CI green → merge.

## Progress (2026-07-07)
- Frontend DONE+verified: jest gate green with src/app included — 95.97/83.11/97.23/97.66, 41 suites / 331 tests. Config: `!src/app/**` → `!src/app/**/layout.tsx`.
- Backend DONE+verified: TOTAL 93.70% (gate 85 active in pytest.ini/test.yml/deploy-dev.yml), 1651 passed 0 failed 7 skipped. Key: `.coveragerc concurrency=greenlet` fixed async undercounting (real baseline was higher than 81.96%); new tests for content/episodes/billing/team/rss/quality_metrics/encryption modules.
- Bonus fixes: audio_snippets patch-target bug (router-local import binding); episode tags filter double-JSON-encode bug in episode_service.py:181 (TDD RED→GREEN, regression test test_get_episodes_filters_by_tags).
- Deslop scan: clean except 2 helper duplications — backend `_register_user`→tests/unit/conftest.py DONE (765 unit tests green); frontend `withOverride`→shared test-util IN PROGRESS.
- Next: commit → opencode/GLM pre-PR review → PR → demo → CI gate → merge.

## Acceptance criteria (from issue)
- [ ] Backend `--cov-fail-under` set to real target (≥85) in gating workflow
- [ ] `src/app/**` no longer wholesale-excluded; only layout/loading/error boilerplate excluded
- [ ] page.tsx / route.ts files under coverage
- [ ] Tests backfilled where coverage drops (gates actually pass)
