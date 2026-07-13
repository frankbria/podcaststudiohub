# Issue #383 — [P4.3.3] Web UI never enables distribution

Status: IN PROGRESS — plan approved autonomously (no architectural fork; rationale below).

## Problem

`generatePodcast` in `apps/web/src/app/(auth)/episodes/[id]/page.tsx:481-484` POSTs
`/api/proxy/generation/episodes/{id}/generate` with no query params. The backend defaults
`enable_distribution=false`, so platform distribution (#316's purpose) is unreachable from
the web UI.

## Key codebase facts (verified by exploration)

- Backend `generate_podcast` (`apps/api/src/routers/generation.py:81-94`) takes
  `enable_distribution: bool = Query(default=False)`. It is honored **only** when ALL of:
  `settings.ENABLE_PLATFORM_DISTRIBUTION` is on (line ~200), `AWS_S3_BUCKET` set (~245),
  and the project has active targets (`is_active`, project- or account-scoped;
  no targets → chain falls through to the normal path, logged, no error).
- `enable_composition` is NOT required for distribution (chain is upload → distribute).
- #378 pre-flight warnings already flow back on the 202 (`warnings: string[]`) and the
  page already toasts them (page.tsx:485-493).
- `/api/proxy/[...path]/route.ts:71-73` forwards query strings verbatim.
- The frontend has NO way to read `ENABLE_PLATFORM_DISTRIBUTION` (no feature-flag
  endpoint exists) and no distribution-target fetch on the episode page.

## Decision (auto-approved, not an architectural fork)

**Always pass `enable_distribution=true` from the generate action.** The issue offers
"automatically or via a checkbox"; automatic is the sanctioned safe default because the
server already performs the exact conditional the issue asks for (flag on + active
targets), and no-ops safely otherwise. A client-side targets fetch would duplicate that
check; a checkbox is unneeded UI (users opt in/out by activating/deactivating targets in
the #316 UI) — YAGNI. Documented as a Known Limitation in the PR (no per-episode opt-out).

## Steps (TDD)

1. Branch `fix/383-web-generate-enable-distribution` off main.
2. RED — `apps/web/__tests__/app/episodes/[id]/page.test.tsx`:
   - Update exact-match assertion (lines ~204-222) to expect
     `/api/proxy/generation/episodes/ep1/generate?enable_distribution=true`.
3. GREEN — page.tsx:482: append `?enable_distribution=true`; update the adjacent comment.
4. Gates: jest (web), lint, tsc; deslop scan; opencode pre-PR review; PR with Known
   Limitations; post-PR opencode review comment; demo (hard gate — outcome evidence that
   the request carries the param); CI green + feedback triage; docs sync; merge.

## Acceptance criteria

- A1: Clicking Generate issues POST `...?enable_distribution=true` through the proxy.
- A2: Backend receives `enable_distribution=true` (proxy forwards query string).
- A3: Warning-toast path (#378) still works unchanged.
- A4: Error paths (non-ok, network) unchanged.
