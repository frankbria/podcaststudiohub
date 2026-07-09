# Issue #341 — [P2.4b] Restore real E2E CI signal (PR-built stack)

Branch: `fix/341-e2e-pr-built-stack`. Plan adapted from CodeRabbit's issue comment; approved autonomously (no architectural fork — both design choices match the AC wording and reuse existing plumbing).

## Already done (verified 2026-07-08, no code needed)
- [x] Dev `Deploy Frontend` ERESOLVE (lucide-react vs React 19): lucide-react no longer in `apps/web/package.json` (hugeicons migration); last two deploy-dev runs green; dev `/login` renders `input[type="email"]`, `/api/health` healthy.
- [x] Four #337 specs (02-projects isolation, 03-episodes isolation, 10-integration journey + concurrent) un-fixme'd in #338/#344; gate thresholds already MIN_PASSED=18 / MAX_SKIPPED=205.

## To do
- [ ] 1. `playwright.config.ts`: env-gated `webServer` array (API uvicorn :8200 w/ `/health`, web `next start` :3200) — active only when BASE_URL is localhost; `reuseExistingServer: !CI`; bumped test/expect timeouts for cold boot.
- [ ] 2. `tests/e2e/global-setup.ts`: apiURL = `API_URL || NEXT_PUBLIC_API_URL || ${baseURL}/api`; preflight API `/health` probe with actionable "unreachable/unhealthy vs login-failed" errors; keep screenshot-on-failure.
- [ ] 3. `.github/workflows/playwright-tests.yml` PR/push path → PR-built stack: postgres:16 + redis:7 services, uv sync + alembic migrate, root `npm ci` (workspaces) + web build with `NEXT_PUBLIC_API_URL=http://localhost:8200`, run env per rm-review.yml conventions (`RATE_LIMIT_ENABLED=false`, CORS `http://localhost:3200`), plain-default E2E creds, keep skip-count gate unchanged as the single authoritative signal.
- [ ] 4. Dev-smoke: keep `workflow_dispatch` path targeting dev; add preflight dev health check that ends the run as skipped/neutral (not failed) when dev is down.
- [ ] 5. `.github/workflows/test.yml`: delete `test-e2e` job; remove from `quality-gate` needs + summary branch.
- [ ] 6. `tests/e2e/README.md`: document PR-built-stack model, dev-smoke variant, local run instructions.
- [ ] 7. Verify locally: run the full E2E suite against the locally-built stack (postgres container + redis), confirm passed>=18.
- [ ] 8. Quality gate → PR → reviews → demo evidence → CI green → merge.

## Acceptance criteria mapping
- PR-built stack via webServer/services → items 1–3
- Single failing-capable E2E signal → item 5
- Clear global-setup diagnostics + non-blocking dev-smoke → items 2, 4
- ERESOLVE fixed → already done (verify only)
- Four #337 specs green on PR-built stack → item 7 + PR CI run

## Archive: Issue #303 — COMPLETE (PR #345 squash-merged 2026-07-07 as a95684b)
Coverage gates real (backend 85 enforced @93.84%, frontend covers src/app). Follow-up: #346 (pytest warnings policy).
