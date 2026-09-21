# #522 — Node 20 EOL → Node 24 LTS (branch feature/issue-522-node-24-lts)
1. RED: `deployment/tests/test_node_runtime.py` pins: `.nvmrc`=24; no `node-version:` literal in workflows, every setup-node uses `node-version-file: '.nvmrc'`; `engines.node` + `@types/node` major == `.nvmrc`; deploy-dev rsyncs `.nvmrc` and selects node via nvm + fails on mismatch before every remote npm/pm2-npm call
2. `.nvmrc` = `24`; 8 `node-version: '20'` → `node-version-file: '.nvmrc'` (rm-review: setup-node moved before `gh pr checkout` so stale PR branches without `.nvmrc` still work)
3. deploy-dev.yml frontend step: rsync `.nvmrc`; `USE_NODE` prelude (source per-user nvm, `nvm install` from `.nvmrc` — idempotent, self-provisions, no global change; fail if major mismatch; log `node -v`) before `npm install`, `npm run build`, `pm2 start npm` (`--interpreter "$(command -v node)"` so a daemon started under system node doesn't run next under it)
4. `engines.node >=24`, `@types/node ^24` + lockfile, dependabot comment, README/DEPLOYMENT_SETUP/setup-demo-vps.sh → 24
- Deviation: VPS `node -v` before-state not captured (auto-mode denies SSH reads); deploy log is the evidence
- [x] all 4 AC — DONE, merged in PR #561 (follow-up #564)

# #540 — [P2.17] Remove the unreachable quality-metrics surface (branch feature/issue-540-remove-dead-quality-metrics)

Verified before deleting: nothing in `src/` writes `generation_progress["quality_metrics"]`
(`grep -rn 'generation_progress\['` → only `tasks/podcast_generation.py` + `tasks/callbacks.py`,
none set the key); `QualityMetricsCalculator` has no importer outside its own tests;
`QualityScoreService` is reached only from the router; `apps/web/src` has zero `quality` hits;
no docs/nginx/e2e reference the prefix. So every `/quality-metrics/*` response is a permanent
404/empty.

1. RED: `apps/api/tests/test_quality_metrics_removed.py` — the app exposes no `/quality-metrics`
   route and `src.routers.quality_metrics` / the two services / the schema module are gone
   (fails on `main` where they all exist).
2. Delete `src/routers/quality_metrics.py`, `src/schemas/quality_metrics.py`,
   `src/services/quality_metrics_service.py`, `src/services/quality_score_service.py`.
3. Unregister: `src/main.py` (import + `include_router`), `src/routers/__init__.py`
   (import + `__all__`).
4. Delete the three test files that only covered the dead code
   (`test_quality_metrics.py`, `test_quality_metrics_endpoint.py`,
   `unit/test_quality_score_service.py`).
5. File the revive half as a follow-up issue blocked on #541 (P2.18), citing this commit so the
   scoring logic is one `git show` away.

- Decision (autonomous, no fork): **removal, not 501** — the issue pre-decided it and grep
  confirms no customer-facing surface calls these endpoints. 501 would keep 1,149 lines of
  src alive to serve an error.
- Decision (autonomous): delete `quality_score_service.py` + schemas too, rather than keeping
  them "for P2.18". A service with zero call sites is the same dead code the issue is about;
  git history is the archive (precedent: #539/PR #567 deleted `ScriptGenerationService` whole).
- Scope: the "now" half only. Done-when boxes 2 and 3 are the revive and belong to the
  follow-up issue, which is what closes them.

- Deviation from step 1: **no RED guard test written.** For a pure deletion there is no
  implementation code to drive, and a test asserting "this module is absent" guards against
  nothing real — a partial deletion (module gone, import left) already fails every test that
  imports the app. Matches the #539/PR #567 precedent, which deleted without a guard test.
  Evidence moved to the demo instead.

## Acceptance criteria
- [x] No endpoint returns a permanent empty result — the surface is removed
- [x] App starts and its route table contains no `/quality-metrics` path
- [x] Revive half filed as a prioritized follow-up blocked on #541 — #570 `[P2.21]`
- DONE, PR #569. Demo: `apps/api/docs/demos/issue540-remove-dead-quality-metrics.md`
  (main: 64 OpenAPI paths, 3 quality routes answering 401 → branch: 61 paths, 0 quality routes,
  404). Suite 1899 → 1802 passed (= the 97 collected tests in the 3 deleted files), 0 failures,
  coverage 94.93% → 94.74%.
- Loose ends found while verifying, filed separately: 9 tracked sample transcripts under
  `apps/api/data/transcripts/` (#309 leftovers, nothing reads them now) and
  `episode_service.py:459 update_generation_status` (zero callers).

# Epic — Replace the podcastfy engine with a thin in-house generation engine

Source: 2026-09-17 deep dive (engine debt vs ElevenLabs' podcast offering). Verdict: keep our own
script layer, drop `podcastfy==0.4.1`, adopt ElevenLabs Text-to-Dialogue (`eleven_v3`) as one TTS
backend. Do NOT move the product onto `POST /v1/studio/podcasts` (enum durations, no own-script
input, single vendor).

Prior art checked: #446 (fork not justified on security alone — this epic is the "reason beyond
security" its doc anticipated), #363 (0.4.3 deferred), #518 (audit-gate toil; its option 4 is this
epic), #32/#21 (transcript validation + quality endpoints, both now dead paths).

## Issues (dependency order)
- Epic  [P2.15] tracking issue
- [P2.16] delete dead `ScriptGenerationService` + tests — independent, first
- [P2.17] quality-metrics endpoints are unreachable — hide now, revive after P2.18 persists transcripts
- [P2.18] engine step 1: in-repo script generation (structured turns, prompts in repo, direct SDK, transcript persisted, real progress)
- [P2.19] engine step 2: TTS adapter interface (ElevenLabs v3 dialogue, Gemini multi, Edge, OpenAI); fixes cwd temp race + global key
- [P2.20] engine step 3: cut over task, remove pin, drop 31 suppressions, docs; closes #518 root cause
- [P3.9] confirm ElevenLabs commercial terms in writing before launch depends on it

## Not filed (YAGNI)
- Studio `create-podcast` "quick mode": revisit only if a customer asks for zero-config generation.
- Interim patch for the gemini_multi cwd race: lands in P2.19; no separate fix.

# #503 — Rate-limiter fail-open observable (branch feature/issue-503-rate-limiter-fail-open-observable)
1. `rate_limiter.py`: warning→error; name the sentinel (`FAIL_OPEN_REMAINING`); count fail-opens in a process-local `fail_open_stats`
2. `dependencies.py`: consume the sentinel — emit a distinct `rate_limit_fail_open` error event with endpoint + ip
3. `/ready`: report `rate_limiter.fail_open_count` / `last_fail_open_at` (informational, does not gate readiness — Redis check already does)
- [x] Redis outage during login → error-level signal   - [x] fail-open observable beyond a log line   - [x] sentinel removed — DONE, merged in PR #556

---

# #518 [P2.10] Audit gate: stop hand-patching unreachable litellm CVEs

DONE — merged in PR #558. Decision (options 2+3 from the issue, autonomous — no fork):
- pip-audit runs with `-f json`; a small gate script classifies findings:
  - package `litellm` → **non-blocking**: `::warning::` annotation + step summary line each
  - id/alias in the enumerated non-litellm ignore list → ignored (unchanged, 11 IDs)
  - anything else → **fails**, listed loudly
  - missing/invalid JSON or skipped deps → fails closed
- The 27 enumerated litellm IDs are deleted.
- Compensating control strengthened: `litellm` must not load *at all* (not just `litellm.proxy`),
  including after constructing `ContentGenerator` exactly as `process_content` does (model_name=None
  → config gemini → ChatGoogleGenerativeAI, not ChatLiteLLM). That makes every litellm advisory —
  proxy or core — unreachable while the test is green.

Steps
1. RED: tests for gate script (subprocess on fixture JSON): litellm-only → exit 0 + warnings;
   ignored non-litellm → exit 0; unknown non-litellm → exit 1; bad JSON → exit 1; skipped dep → exit 1
2. GREEN: `apps/api/scripts/pip_audit_gate.py`; `security-audit.sh` runs pip-audit json → gate
3. Strengthen `test_dependency_reachability.py` litellm probe
4. Docs: script header + `docs/podcastfy-advisory-reachability.md` record the decision and the
   compensating control

Done when
- [x] New litellm advisory does not block unrelated PRs
- [x] Reachable (non-litellm, unlisted) advisory still fails loudly
- [x] Replacement documented in script header + reachability doc
- [x] Decision records test_dependency_reachability.py as the compensating control

## #530 — deterministic tiebreak on paginated list queries (2026-09-18)
- [x] tests/pagination_tiebreak.py helper: force created_at tie, page 2-at-a-time, assert ids == id order
- [x] one tie test per service: projects, episodes (sort_by created_at asc+desc), episode_layouts, content, tts_configs, conversation_templates, distribution_targets, teams, RSS _get_completed_episodes (stable across two calls)
- [x] append `<Model>.id` (same direction) as final sort key at every site; episode_service after the chosen sort_column
- Decisions: teams list added (paginated, not in issue list); unpaginated get_members/get_invitations left alone.

## [P2.16] #539 — delete dead ScriptGenerationService (branch feature/issue-539-delete-dead-script-service)
Plan source: issue body ("Fix"). No architectural fork — approved autonomously.
1. `git rm` `src/services/script_generation_service.py` (586) + `tests/test_script_generation.py` (1302)
2. Drop the `ContentGenerator` import from the `main.py` lifespan guard — it existed only for this service
3. Keep `tests/test_imports.py` and `tests/test_dependency_reachability.py` as-is: they import
   `ContentGenerator` to test the *package install* and the CI-enforced advisory-reachability claims
   (#446), not this service. Deleting those imports would weaken a deliberate CI gate.
4. Coverage: file was 97.31% of 186 stmts; overall 94.88% → 94.81% projected. Gate is 85%, no risk.
- Deviation from the issue: the `podcastfy-0.4.3-evaluation.md` row justified "no impact" by pointing at
  `script_generation_service.py` pinning `GEMINI_MODEL_NAME`. With the service gone the live path pins
  **no** LLM model, so the 0.4.3 default change *would* swap our model. Row rewritten to say so.
