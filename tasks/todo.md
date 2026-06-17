# Release-Readiness Plan — podcaststudiohub

**Audit date:** 2026-06-13 · **Verdict:** 🔴 NOT READY (9 blockers) · **Issues:** #204–#226 (23 total)

Generated from a multi-agent audit (10 reviewers + adversarial verification). Each issue
carries file:line evidence + acceptance criteria on GitHub. Titles are phase-tagged `[PX.Y]`
so issue order == work order.

> The **9 blockers** are #204, #205, #206, #207, #208, #209, #210, #211, #212 — they span
> Phases 1–3 (not every Phase 1/2 item is a blocker: #213, #214, #217 are high/medium correctness
> fixes, not release blockers). The release gate below requires Phases 1–3 done.

> ⚠️ **The core mirage:** the app "seems to work" only because the test suite **mocks the
> generation engine**. Against the pinned `podcastfy==0.4.1` (pip-installed in the venv — there
> is **no** `podcastfy/` engine in the repo; `podcast-generator/` is empty scaffolding),
> **every** generation call fails (`#204`). Fixing that + replacing mocked tests with a real
> end-to-end demo is the gate to "ready-with-caveats".

---

## Phase 1 — Stop the bleeding (urgent security, mostly independent)
- [x] **P1.1 #207** Rotate live AWS/OpenAI/ElevenLabs/Gemini/Transistor keys ✅ done 2026-06-14 (old AWS key deactivated; verified never committed to git; S3 object policy added)
      → **Frank rotates** (deactivate the flagged AWS access key — ID is in issue #207 — in IAM). Secret scanner ✅ done (see below).
- [ ] **P1.2 #205** JWT verification ignores `type` claim — verification/refresh tokens usable as access tokens
- [x] **P1.3 #206** SSRF — content URLs + webhook targets fetched server-side, no private-IP/metadata block ✅ done 2026-06-14 (PR #235; guard at validation+dispatch, redirects constrained; residual DNS-rebinding tracked as P4.7 #234)
- [x] **P1.4 #212** Backend JWT exposed to browser JS (NextAuth session) + leaked in SSE `?token=` URL ✅ PR #237 (server-side /api/proxy; SSE query-token path removed)

## Phase 2 — Restore the core product (generation pipeline)
- [ ] **P2.1 #204** 🔴 `generate_podcast()` called with invalid kwargs → **every generation fails**. *Unblocks the rest of Phase 2.* Add an autospec/signature-asserting test; pin `podcastfy==0.4.1`.
- [ ] **P2.2 #213** `/regenerate` passes wrong positional args → guaranteed 500, leaves episode degraded
- [x] **P2.3 #217** Episode `tts_model`/`conversation_config` never forwarded → always OpenAI TTS ✅ done (generation.py eager-loads tts_config/template, normalises gemini_multi→geminimulti, forwards to task)
- [x] **P2.4 #214** No guard against re-submitting generation for an in-progress episode (race) ✅ 409 guard in generate_podcast (`_RESTARTABLE_STATUSES`); regenerate inherits it; unit+integration tests
- [ ] **P2.5 #210** PDF/file input non-functional — no upload endpoint; extraction ignores S3 key *(needs StorageService + #204)*
- [x] **P2.6 #211** Distribution subsystem unreachable + would publish blank episodes ✅ PR #243 (router loads active targets → platforms dict; task populates metadata from Episode+s3_url; compose→upload→distribute ordering; no-publish-without-uploaded-audio guard; Spotify audio_url fix)

## Phase 3 — Deployment hardening (gate before any prod deploy)
- [ ] **P3.1 #208** nginx serves authenticated SaaS over plain HTTP — enable TLS + HSTS/CSP/security headers
- [ ] **P3.2 #209** Deploys as root, uvicorn bound `0.0.0.0` (bypasses nginx); reconcile 8000/8001 port mismatch
- [ ] **P3.3 #224** Harden CI/agentic workflows — issue-title shell injection, dispatch-input injection, SHA-pin actions

## Phase 4 — Correctness & authz mediums
- [ ] **P4.1 #215** Inconsistent S3 key layout — workflow-chain path drops `user-{id}/` tenant prefix *(after #204/#210)*
- [ ] **P4.2 #220** finalize task runs upload inline (no retry); SSE session leak; wrong status in `on_upload_complete`
- [ ] **P4.3 #216** Stripe webhook signature bypass when secret unset *(latent — Stripe currently unreachable)*
- [ ] **P4.4 #218** Invitation acceptance not bound to invited email; team tables lack RLS backstop
- [ ] **P4.5 #219** `expires_in` hardcoded 86400 but JWT expires in 30 min *(relates to #205)*
- [ ] **P4.6 #222** No server-side route protection (middleware) for the `(auth)` group — defense-in-depth
- [ ] **P4.7 #234** IP-pin outbound fetches to close the residual DNS-rebinding SSRF TOCTOU *(fast-follow to #206/P1.3, which is done; core SSRF already mitigated — this is defense-in-depth, not a release blocker)*

## Phase 5 — UX, tech-debt, docs
- [ ] **P5.1 #221** TTS "Save Configuration" creates broken ElevenLabs configs (no voice-ID input) *(do after #217)*
- [ ] **P5.2 #223** Adopt or delete the dead `api-client` layer; fix signup loading; minor UX
- [ ] **P5.3 #226** Replace hardcoded gray Tailwind colors with design tokens; minor robustness nits
- [ ] **P5.4 #225** Rewrite CLAUDE.md/README for the SaaS monorepo; fix broken refs & config drift *(do last so docs reflect fixes)*

---

## Cross-phase dependencies
- `#204` (P2.1) gates meaningful work/testing on `#213 #217 #210 #211 #214 #215`.
- `#221` (P5.1) is only meaningful once `#217` (P2.3) forwards TTS config.
- `#210` (P2.5) needs `StorageService.download_file` wired (already exists, unused).
- `#225` (P5.4) last — so docs describe the fixed system.
- `#234` (P4.7) depends on `#206` (P1.3, done) — IP-pinning hardening of the shipped SSRF guard.

## Secrets / secret-scanner status
- ✅ **gitleaks pre-commit hook installed** (`.pre-commit-config.yaml`, `pre-commit install` run). gitleaks
  passed on all tracked files (no committed secrets; the live keys are in gitignored `.env` only).
- ✅ **Rotated 2026-06-14** — all keys cycled, old AWS key deactivated; full-history scan confirmed
  the keys were never committed/pushed (precautionary rotation, not a leak); S3 object policy added (#207 closed).
- Recommend moving real secrets to a secret manager / CI secrets; keep placeholders on dev machines.

## Release gate (Definition of Done for "ready-with-caveats")
1. Phase 1 + Phase 2 complete and **verified by a real, non-mocked end-to-end generation demo**
   (URL → transcript → audio → S3 → playable episode).
2. Phase 3 complete: HTTPS in front, non-root deploy, hardened CI.
3. New tests exist for: generation kwargs (autospec), `/regenerate`, webhook signature, SSRF rejection,
   route protection — so green CI reflects a working product.
4. P4/P5 can trail into a fast-follow milestone if explicitly accepted as known caveats.

---

## Active work — Issue #214 (P2.4): no guard against re-submitting an in-progress generation

**Plan source:** comment (CodeRabbit coding plan), adapted to the codebase.

**Problem:** `POST /generation/episodes/{id}/generate` dispatches a new Celery task
regardless of `generation_status`. A second submission while one is in flight races to
write `s3_url`/`s3_key`/`generation_status`, and overwrites the in-progress
`celery_task_id` in `generation_progress` so SSE only tracks the newer task.

**Verified:** `Episode.generation_status` is a Text column (default `'draft'`); the
generate endpoint sets it to `"queued"` on dispatch. `regenerate_podcast` delegates to
`generate_podcast`, so it inherits any guard added there. The existing
`test_generation_router.py` already has an `episode_and_auth` fixture +
`_create_text_source` helper to drive a real dispatch with Celery mocked.

### Step 1 — Add in-progress guard (`apps/api/src/routers/generation.py`)
- [x] Module constant `_RESTARTABLE_STATUSES = frozenset({"draft", "complete", "failed"})`.
- [x] In `generate_podcast`, immediately after the 404 check, if
      `episode.generation_status not in _RESTARTABLE_STATUSES` raise
      `HTTPException(status_code=409, detail=...)` naming the current status. Placed before
      content assembly so an in-flight episode is rejected before any Celery dispatch.

### Step 2 — Tests (existing `apps/api/tests/test_generation_router.py`)
- [x] `test_generate_rejects_when_already_in_progress` — integration: first POST → 202
      (status `queued`), second POST → 409 and `delay` not called again.
- [x] `test_generate_allowed_from_restartable_status[draft/complete/failed]` — unit: each
      restartable status passes the guard and dispatches.
- [x] `test_generate_rejects_each_in_progress_status[queued/extracting/generating/uploading/
      composing/distributing]` — unit: every in-flight status → 409, no dispatch.

### Acceptance criteria
- [x] Reject with 409 when `generation_status` is in an in-progress set
      (queued/processing/uploading/composing/distributing/…).
- [x] Test asserting the 409 / idempotent behavior.
- [x] Full api suite green (661 passed); ruff clean.

### Deviations from CodeRabbit's plan
1. **Tests in existing `test_generation_router.py`** (not a new file — it already exists
   with the right fixtures).
2. **Guard = "NOT in {draft, complete, failed}"** (CodeRabbit design choice 2) — covers all
   current/future in-progress states, matching the issue's listed set.
3. **Used unit tests (mocked episode) for the allow/deny matrix** instead of DB-status
   mutation — the shared RLS test-DB session can't be re-read through the API after a
   direct status write (mirrors `test_regenerate_does_not_degrade_episode_on_failure`).
4. **Fixed a pre-existing mis-mock** in `test_regenerate_endpoint.py`: it stubbed
   `scalar_one_or_none` but the query uses `.unique().scalar_one_or_none()` (from #217),
   so the guard saw an unconfigured MagicMock. Aligned the mock to the real query shape.

---

## Active work — Issue #210 (P2.5): PDF/file input non-functional

**Plan source:** comment (CodeRabbit coding plan), adapted to the codebase.
**Branch:** `fix/210-pdf-upload-s3-extraction`

**Problem:** The `pdf` source type requires `s3_key`+`filename`, but (1) there is no upload
endpoint to store a PDF and create the record, and (2) `extract_from_pdf` ignores `s3_key`
and reads a hard-coded `data/uploads/{filename}` local path that nothing writes → every PDF
extraction fails with FileNotFoundError.

**Verified in codebase:** content router has no prefix (routes `/episodes/{id}/content`,
`/content/{id}`); settings use `AWS_S3_BUCKET`/`AWS_REGION`; `StorageService.download_file`
exists but is unused; `audio_snippet_service` is the canonical multipart→S3→record pattern
(module-level `_upload_to_s3` helper, mocked in tests); `validators.py` already has
`sanitize_filename`. **`generation.py` was already refactored by #214/#217** to reject
unextracted file/pdf sources (HTTP 400) and feed the engine `extracted_content` — it no
longer passes raw `s3_key` to the engine.

### Steps
- [ ] **1. PDF validation util** (`src/utils/validators.py`): `validate_pdf_format(filename,
      content_type)`; `MAX_PDF_SIZE_BYTES = 50MB`.
- [ ] **2. PDF upload service** (`src/services/content_service.py`): `upload_pdf_content(...)`
      + module helper `_upload_pdf_to_s3` (None in dev when `AWS_S3_BUCKET` unset). S3 key
      `content/{tenant_id}/{episode_id}/{uuid}_{sanitized}`.
- [ ] **3. Upload endpoint** (`src/routers/content.py`): `POST /episodes/{episode_id}/content/upload`
      (multipart `file`, `description`, `auto_extract=True`); dispatch extract task when `auto_extract`.
- [ ] **4. Fix PDF extraction (CORE)** (`src/services/content_extraction_service.py`): remove TODO +
      `data/uploads/`; download `s3_key` via `StorageService.download_file` to a temp `.pdf`; extract;
      `os.unlink` in `finally`; clear error when storage unconfigured/download fails.
- [ ] **5. StorageService async-safe** (`src/services/storage_service.py`): wrap boto3
      `download_file`/`upload_file` in `asyncio.to_thread`.
- [ ] **6. Tests**: `test_content.py` (upload success/wrong-ext/wrong-type/oversize/source_data);
      `test_content_extraction.py` (mock `download_file`, assert s3_key + temp cleanup, replace old
      `data/uploads/` assertion); new `test_pdf_pipeline_integration.py` (upload → extract → generate,
      `pending→extracting→complete`).

### Acceptance criteria
- [ ] Multipart upload endpoint stores PDFs to S3 and records `s3_key`/`filename`.
- [ ] Extraction downloads from S3 via `StorageService.download_file`; TODO removed.
- [ ] `s3_key` resolved to text before the engine (via extraction → `extracted_content`).
- [ ] Integration test: upload → extract → generate.

### Deviations from CodeRabbit plan
1. **Phase 2 Task 2 (generation router file_paths) is obsolete** — already handled by #214/#217;
   the AC "resolve s3_key before the engine" is met via the extraction path. Re-adding raw-path
   passing would regress that design (podcastfy 0.4.1 has no file-path kwarg), so `generation.py`
   is left unchanged.
2. Settings keys are `AWS_S3_BUCKET`/`AWS_REGION` (not `S3_BUCKET_NAME`).
3. Reuse existing `sanitize_filename`; no new shared S3→temp helper needed (generation untouched).

---

## Active work — Issue #211 (P2.6): distribution unreachable + publishes empty metadata

**Plan source:** comment (CodeRabbit coding plan), adapted to verified current code.

**Problem (verified):**
1. `routers/generation.py:229-236` dispatches `generate_podcast_task.delay(...)` without
   `platforms=`; task default `platforms=None`. Distribution gate
   `enable_distribution and bool(platforms)` (podcast_generation.py:175-177) is never true →
   distribution always skipped. No code loads active DistributionTarget rows.
2. `build_generation_workflow` hardcodes `episode_metadata={}` (podcast_generation.py:511) →
   Spotify/Apple/webhook would publish blank title/description and no audio_url.
3. `spotify_service.publish_episode` maps audio to read-only `audio_preview_url`
   (spotify_service.py:111).

**Verified:** task already declares (unused) `platforms` param; `distribute_to_platform_task`
already decrypts `config` via `_decrypt_platform_config` (so router passes raw encrypted
config); `on_upload_complete` (callbacks.py:75) sets `Episode.s3_url` as the first chain
stage → metadata must be populated *in the task* (post-upload), not at workflow-build time;
sync DB access pattern is `with SyncSessionLocal() as db: db.get(Episode, UUID(id))`.

### Step 1 — Service: active-targets query (`services/distribution_target_service.py`)
- [ ] `get_active_distribution_targets_for_project(db, project_id)` (async): filter
      `project_id` + `is_active == True`, newest-first; return `list[DistributionTarget]`
      (raw encrypted `config`; decryption stays in the task).
- [ ] Unit tests (async test_db): only-active; project filter; excludes inactive; empty when none.

### Step 2 — Router: build + pass platforms dict (`routers/generation.py`)
- [ ] When `use_distribution`, load active targets for `episode.project_id`, build
      `platforms = {t.target_type: t.config for t in targets}`, pass `platforms=platforms`
      to `.delay()` only when non-empty.
- [ ] Integration test: active target + `enable_distribution=true` → `delay` called with
      `platforms` = `{target_type: config}`.

### Step 3 — Task: populate metadata at distribution time (`tasks/platform_distribution.py`)
- [ ] Load Episode via `SyncSessionLocal`; merge DB metadata under any passed-in (passed-in
      wins): title/description/explicit/publish_date ← `episode.episode_metadata`;
      duration_seconds ← `episode.duration_seconds`; audio_url ← `episode.s3_url`.
- [ ] Extract pure helper `_merge_episode_metadata(episode, passed)` for direct unit testing.
- [ ] `build_generation_workflow` keeps `episode_metadata={}` + comment explaining the task
      self-populates from the fresh row (avoids stale pre-upload s3_url).
- [ ] Tests: helper merge + precedence; task populates non-empty title/description/audio_url.

### Step 4 — Spotify mapping + docs (`services/spotify_service.py`)
- [ ] Replace `audio_preview_url` with `audio_url` in payload; comment noting Spotify for
      Podcasters primarily ingests via RSS and direct API publishing has platform limitations.

### Acceptance criteria
- [ ] Active targets loaded; `platforms` dict built; `platforms=` passed to `.delay()`.
- [ ] `episode_metadata` populated (title/description/duration/explicit/audio_url) from Episode + S3 URL.
- [ ] Spotify/Apple mechanism documented; `audio_preview_url` mapping fixed.
- [ ] E2E test asserts distribution dispatch with non-empty metadata when a target is configured.

### Known limitations (carry to PR)
- Account-level targets (`project_id IS NULL`) are not auto-distributed; only project-scoped
  active targets are loaded (matches AC wording).
- Spotify/Apple direct-publish stays best-effort (design-choice option 1: fix mapping +
  document); no new Podcasters/Connect API integration.

---

## Ops changes already made this session
- README server IP removed (commit `bf9e606`).
- gitleaks pre-commit secret scanner added.
- Issues #161 / #162 (agentic noise) closed as not planned.
- Disabled (reversible via `gh workflow enable "<name>"`): Community Response, Issue Triage,
  PR Review, and all 6 Repo Maintainer workflows. **Kept active:** Test Suite, Deploy to Development,
  Playwright E2E, Draft PDF, Claude Code (manual `@claude` helper).
- Helper scripts: `scripts/create_audit_issues.py`, `scripts/renumber_audit_issues.py`,
  `scripts/audit_issue_map.json`.
