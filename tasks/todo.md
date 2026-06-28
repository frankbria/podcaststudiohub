# Issue #302 [P2.4] — Re-enable E2E suite & restore real CI signal

**Branch:** `fix/302-e2e-test-trust`
**Goal:** Stop CI false-green: fix broken helper selectors, provision real two-session isolation tests, selectively re-enable headline + isolation specs, add a skip-count CI gate, correct the README.

## SCOPE NARROWED (user decision 2026-06-28)
Re-enabling the isolation/journey specs uncovered a real app bug: **project/episode
creation is broken** by a web<->API contract mismatch (web sends `title`; backend
requires `name`/`*_metadata`) + `GET /projects` 500s. Filed as **#337 (P2.4a)**.
Per user: ship test-trust infra now; keep isolation/journey specs written but
`fixme`'d behind #337; re-enable only auth/route-protection (passes today).

## Acceptance criteria (from issue)
- [x] Fix selectors to current UI (helpers repaired + tsc-clean)
- [x] Provision two independent authenticated sessions (User B in global-setup) + negative assertions written
- [~] Re-enable headline journey + isolation specs — written & ready, `fixme`'d behind #337; auth route-protection re-enabled & passing
- [x] CI fails on skip-count above threshold (skip-gate, self-tested)
- [x] Correct README coverage claims

## Plan adaptations (verified against code — not in the issue's plan)
1. **User B via global-setup, not per-test signup.** Dev registration is rate-limited 3/hr/IP (`01-auth.spec.ts:8`). Self-provisioning fresh users per isolation test = 4-5 regs/run -> flaky. Provision one deterministic, idempotent User B in `global-setup`, persist `user-b.json`, reuse across isolation tests. User A = existing shared `user.json`.
2. **Headline journey stops before live generation.** Re-enable signup->project->episode->content->assert "Generate Podcast" visible. Keep the real generate->wait->download flow `fixme` (depends on #313/#314; 5-min live TTS is flaky/costly in CI).

## Steps

### Phase 1 — Repair shared helpers (selectors -> real UI)
- [ ] `episode-helpers.ts`: createEpisode (#episode-title, dialog-scoped submit, nav /episodes/{id}); addContentSource (URL/Text toggle aria-pressed, #content-url/#content-text, scoped submit); generatePodcast (Generate Podcast, valid `Status: queued` locator); waitForGeneration (valid `Status: complete`, long timeout); verifyAudioPlayer (audio[controls] + Download MP3 aria-label); deleteContentSource (aria-label="Delete content source" + ConfirmDeleteDialog).
- [ ] `project-helpers.ts`: createProject (#project-title/#project-description, dialog-scoped submit — trigger&submit share "Create Project" text = strict-mode trap; nav via card `[role=button][aria-label="Open project: <t>"]`); deleteProject (aria-label="Delete <t>" + ConfirmDeleteDialog).
- [ ] `auth-helpers.ts`: logout via `[aria-label="User menu"]` -> Logout; add User B context loader.

### Phase 2 — Two-session isolation + selective re-enable
- [ ] `global-setup.ts`: register + browser-login User B (deterministic email from User A, idempotent), save `tests/e2e/.auth/user-b.json`.
- [ ] `02-projects.spec.ts`: drop top-level fixme; keep CRUD/validation/nav sub-describes fixme; rewrite "Project Access Control" — User A creates, User B (separate context) blocked + negative assertion.
- [ ] `03-episodes.spec.ts`: same pattern for "Episode Access Control".
- [ ] `10-integration.spec.ts`: drop top-level fixme; re-enable trimmed "Complete User Journey" (stop at Generate visible) + "Concurrent User Workflow" isolation (two contexts); re-fixme generation/download/counts/edit/perf/mobile sub-describes targeting unverified UI.
- [ ] `01-auth.spec.ts`: re-enable the 3 route-protection test.fixme cases using real logout.

### Phase 3 — CI skip-gate + docs
- [ ] `playwright.config.ts`: add json reporter -> `playwright-report/results.json`.
- [ ] `playwright-tests.yml`: after test run (test job, `if: always()`), parse `.stats.skipped`, emit GitHub notice (passed/failed/skipped), fail if skipped > THRESHOLD (documented; tuned from first CI run).
- [ ] `tests/e2e/README.md`: replace "270 tests / Implemented" with active-vs-fixme reality; fix helper descriptions.

### Quality gate
- [ ] playwright `--list` parses (valid fixme structure); skip-gate self-tested on sample JSON; CI Playwright run green — tune THRESHOLD from actual count.
