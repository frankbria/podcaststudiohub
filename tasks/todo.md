# Issue #341 — COMPLETE (PR #347 squash-merged 2026-07-09 as 3c3f1a4, issue closed)

Branch: `fix/341-e2e-pr-built-stack`. Plan adapted from CodeRabbit's issue comment; approved autonomously (no architectural fork — both design choices match the AC wording and reuse existing plumbing).

## Already done (verified 2026-07-08, no code needed)
- [x] Dev `Deploy Frontend` ERESOLVE (lucide-react vs React 19): lucide-react no longer in `apps/web/package.json` (hugeicons migration); last two deploy-dev runs green; dev `/login` renders `input[type="email"]`, `/api/health` healthy.
- [x] Four #337 specs (02-projects isolation, 03-episodes isolation, 10-integration journey + concurrent) un-fixme'd in #338/#344; gate thresholds already MIN_PASSED=18 / MAX_SKIPPED=205.

## To do
- [x] 1. `playwright.config.ts`: env-gated `webServer` array (done; timeout bumps skipped — localhost prod build showed zero flakiness, 19 passed in 11s)
- [x] 2. `tests/e2e/global-setup.ts`: preflight + diagnostics (negative path exercised: dead API → clear env-problem error)
- [x] 3. `playwright-tests.yml` PR-built stack — **plus dev-parity RLS roles**: first local run FAILED isolation specs because the bootstrap superuser bypasses FORCE RLS; CI now migrates as BYPASSRLS `podcastfy_user`, API runs as RLS-subject `podcastfy_app` (lesson recorded)
- [x] 4. Dev-smoke preflight (verified live: dispatch run 28989743173 — healthy dev detected, auth suite 15 passed against dev)
- [x] 5. `test.yml` `test-e2e` deleted + quality-gate refs removed
- [x] 6. README updated (execution model + exact local recipe)
- [x] 7. Local verify: 19 passed / 0 failed / 200 skipped; CI PR run 28989440713 identical (passed=19 skipped=200)
- [x] 8. PR #347 merged; opencode reviews done (pre-PR "ship it" + post-PR: billing-402 Major fixed in 7dcecb6); demo posted; awaiting CI green on HEAD → final triage → merge. GitGuardian red = false positive on documented throwaway CI literals (same convention as test.yml on main); no branch protection.

## Acceptance criteria mapping
- PR-built stack via webServer/services → items 1–3
- Single failing-capable E2E signal → item 5
- Clear global-setup diagnostics + non-blocking dev-smoke → items 2, 4
- ERESOLVE fixed → already done (verify only)
- Four #337 specs green on PR-built stack → item 7 + PR CI run

## Archive: Issue #303 — COMPLETE (PR #345 squash-merged 2026-07-07 as a95684b)
Coverage gates real (backend 85 enforced @93.84%, frontend covers src/app). Follow-up: #346 (pytest warnings policy).
