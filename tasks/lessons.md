# Lessons

## 2026-07-10 (#313)
- **Use the Edit/Write tools for file content — including appends.** Slipped
  into `cat >> file << 'EOF'` to append a test class; the context rule bans
  heredoc/echo redirection for file writing, and Edit anchored on the file's
  tail does the same job reviewably.

## 2026-07-10 (#312, PR #371)
- **Demo against the real schema, not mocks — it catches what mocked suites
  structurally can't.** The #312 demo (real task + real Postgres, only HTTP
  stubbed) crashed on `episodes_status_check`: migration 001 never allowed
  `distributing`/`composing`/`uploading`/`distribution_failed`, so every
  distribution callback's write had been silently failing in production (the
  except-and-log swallowed the CheckViolation). 1717 mocked/API tests were green
  through it. Pairs with the standing "verify pg_constraint, not model files"
  lesson — model-metadata `create_all` would also have hidden it.
- **Suite-order poisoning: mocked-podcastfy workflow tests break psycopg Jsonb
  adaptation** for any later sync-ORM JSONB insert (`cannot adapt type 'Jsonb'`).
  Bisect with `pytest <suspect>.py <victim>.py`; filed #372. Workaround: assert
  DDL via `pg_get_constraintdef` (SELECT-only) instead of inserting rows.
- **Migration downgrades must handle data the upgrade enabled.** Re-narrowing a
  CHECK fails validation once rows carry the new values — normalize them in
  `downgrade()` first. (Caught by post-PR GLM review; verify with a local
  `alembic downgrade && upgrade` round-trip.)

## issue-lifecycle: skill invocation authorizes the whole flow through merge
- **2026-06-26 (#296/PR #331):** During an autonomous tick I finished the
  implementation but held push/PR/merge waiting for plan re-confirmation. User:
  "What confirmation is outstanding? You should be approved to go all the way
  through PR merge." When the user explicitly invokes `implementing-issue-plans`
  (or `next-issue`), that invocation *is* the approval to run through merge —
  especially when the plan came from an existing issue comment (not
  self-authored). Don't pause the loop for re-confirmation; the real gates
  (CI green, demo with outcome evidence, bot-finding triage) still protect the
  merge. Hold only on genuinely new/irreversible decisions outside the
  authorized lifecycle.

## Mass-assignment fix: verify "nothing internal uses this" against actual callers
- **2026-06-23 (#271/PR #278):** Plan 005 assumed only the Celery pipeline wrote
  episode system fields and that nothing internal went through `update_episode`.
  Grep proved **two** services (`script_generation_service`, `quality_metrics_service`)
  wrote system fields *through* `update_episode` — a blanket service allowlist would
  have silently dropped those writes. Before adding a guard to a shared mutator,
  `grep` every caller; route legitimate internal writers through a dedicated bypass
  (`set_episode_system_fields`) rather than weakening the guard.
- **Latent bug surfaced:** `quality_metrics_service` was calling
  `update_episode(db, episode_id, {dict})` — wrong signature; only "passed" because
  the test mocked `update_episode`. Mocks hide signature drift; prefer a real-DB
  persistence test for write paths.
- **JSONB in-place mutation doesn't persist:** reassigning a plain (non-Mutable)
  JSONB column with the *same* dict reference after mutating it in place is not
  detected by SQLAlchemy → the write silently no-ops. Build a NEW dict
  (`dict(obj.col or {})`) before adding keys. A regression test that fails on the
  aliasing version and passes on the copy version is the proof.


## Dependency security bumps: prefer `npm update <pkg>` over `npm audit fix`
- **2026-06-23 (#272/PR #277):** `npm audit fix` (non-`--force`) on this workspaces
  monorepo churned ~11k lockfile lines and bumped jest's transitive tooling
  inconsistently → broke the test runner (`this._moduleMocker.clearMocksOnScope is
  not a function`, 35/37 suites failed to *run*). Reverting and using
  `npm update next` produced a small, targeted lockfile diff that cleared the HIGH
  `next` advisory with all 244 web tests + build green.
- **Pattern:** for a single-package security bump, do `git checkout package-lock.json`
  (revert any broad fix) then `npm update <pkg>` to touch only that subtree. Reserve
  `npm audit fix` for when you actually want the whole tree reconciled, and re-run
  the full test suite immediately after.
- **Verify it's a regression vs. pre-existing:** when a gate fails after a dep
  change, check whether the failing package's lockfile entry actually changed
  (`git diff package-lock.json | grep <pkg>`) before "fixing" — most of the
  `tsc --noEmit` errors here were pre-existing on `main`, not caused by the bump.

## tsc green locally but red in CI = phantom @types dependency (#280)
- **Symptom:** `npm run typecheck` exits 0 locally; CI fails with `Cannot find name
  'expect'/'it'/'describe'`, `Cannot use namespace 'jest' as a value`.
- **Cause:** `@types/jest` was hoisted into the local root `node_modules` (from some
  prior/global install) but declared in NO package.json and absent from the lockfile.
  A clean `npm ci` in CI doesn't get it, so tsc loses the ambient test globals.
- **Pattern:** before trusting a local `tsc` pass for a new CI gate, check that every
  `@types/*` the code relies on is actually declared (`grep @types/ package.json`) and
  in the lockfile (`grep node_modules/@types/<x> package-lock.json`). Fix by adding the
  missing `@types/*` to the workspace devDeps — don't chase it as a code error.
- **Related:** jest-dom only augments `jest.Matchers`; the base globals (`expect`/`it`/
  `describe`/`jest`) come from `@types/jest`, a separate dependency.

## Resource-leak fix: clean up on EVERY terminal path, not just the success path
- **2026-06-25 (#275/PR #283):** Plan 009 scoped the composed-audio temp-file cleanup
  to the success path only. But the file is disposable wherever **no retry will read it
  again** — that's three terminal paths, not one: success, retries-exhausted
  (`MaxRetriesExceededError` → return "failed"), and **non-retryable errors that
  re-raise immediately** (the last one was missed in the first pass and caught by
  `codex review`). The retry path is the only one that must keep the file.
- **Pattern:** when fixing a "temp/resource leaks" bug on a Celery (or any retrying)
  task, enumerate every exit: success return, each terminal-failure return, AND each
  `raise`/re-raise branch. Anywhere the task ends with no further retry, the resource
  is disposable. A success-only guard re-creates the same leak from the failed tail.
- **Process:** a human reviewer (m13v) flagged the exhausted-retries gap on the issue;
  `codex review` (cross-family) flagged the non-retryable-raise gap on the PR. Both
  were real. Verify-before-fix held: each "missing cleanup" claim was confirmed against
  the actual control flow (and that no later workflow task reads the local file) before
  extending scope beyond the written plan.

## Seeding analytics_events directly needs real episode/project FK parents (#274)
- **2026-06-25 (#274/PR #289):** A characterization test that inserts `AnalyticsEvent`
  rows on the `test_db` session with random `episode_id`/`project_id` UUIDs fails with
  `ForeignKeyViolationError` — the table has FKs to `episodes`/`projects`. The
  `analytics_events` table itself has **no RLS policy** (only a `tenant_id` column, no
  FK), so `tenant_id=uuid4()` is fine, but the episode/project FKs are enforced.
- **Pattern:** the `client` fixture yields the *same* session as `test_db`, so create the
  real project + episode via the API first (`/auth/register` → `/projects` → `/episodes`),
  then seed events directly with those IDs and custom `created_at`/`device`/`country`/
  `metadata` the API can't set. Best of both: real FK parents + arbitrary event attrs.
- **Contract preservation proof:** the strongest evidence a refactor preserves a return
  shape is running the *new* characterization test against the *old* code (`git show
  HEAD~1:path > svc.py`, swap, run) — it must pass on both. Identical output = contract held.

## Postgres week numbering ≠ Python strftime("%W") (#274)
- Don't reach for `to_char(created_at, 'IW')`/ISO week to replace
  `dt.strftime("%Y-W%W")` — they use different week-numbering conventions and would
  silently change a frontend-facing key. When pushing aggregation to SQL but a Python
  date-format must be preserved exactly, `GROUP BY func.date(created_at)` (O(days), not
  O(events)) and apply the *same* Python `strftime` to the grouped dates. Keeps the
  format byte-for-byte while still avoiding row materialization.

## Moving runtime state to Redis breaks existing integration tests (#273)
- When converting an in-memory store (module dict) to a real Redis client, existing **integration** tests that exercise the endpoints now hit the real client. They pass locally if a Redis happens to be running, but the backend CI job has **no Redis server** (rate limiting is disabled; rate-limiter tests mock Redis).
- Before pushing: run the affected gate with a dead `REDIS_URL` (e.g. `REDIS_URL=redis://localhost:1/0 uv run pytest ...`) to simulate CI, not just with local Redis up.
- Fix pattern: back the store with a tiny in-memory fake via an autouse fixture (setex/getdel) — no new dependency, no infra.

## DB backup/restore scripts: atomicity + scoped pruning (#293/PR #328)
- **2026-06-26:** codex cross-family review caught two data-loss risks the first pass missed (CodeRabbit was rate-limited and never ran — its green check was a no-op, so the cross-family pass mattered).
- `pg_restore --clean` is **not atomic**: a mid-restore failure leaves the live DB half-dropped. Always add `--single-transaction --exit-on-error` so a failed restore rolls back instead of corrupting prod.
- A retention prune that deletes "everything older than N days under the prefix" will nuke **unrelated** objects sharing that prefix. Scope deletes (and "latest" selection) to the script's own filename pattern (`podcastfy-<stamp>.dump`), never the bare prefix.
- Demo an infra script's risky logic for real even without the prod deps: ran the actual pg_dump→pg_restore round-trip inside the running `postgres:16` docker container (recovered exact rows), and replayed the prune date-comparison against simulated `aws s3 ls` output. Outcome evidence, not just "exit 0".

## Celery `bind=True` error callbacks are dispatched OLD-STYLE (task_id only) (#294/PR #329)
- **2026-06-26:** codex flagged it; verified against `celery/backends/base.py::BaseBackend._call_task_errbacks` in 5.5.3. For a `bind=True` errback task, `errback.type.__header__` is a `partial`, so Celery skips the new-style `errback(request, exc, traceback)` path and calls it with **only** `(task_id,)`. `on_workflow_failure(self, task_id, exc, traceback, ...)` therefore raised `TypeError` (missing exc/traceback) every time it fired as a `link_error` — so episodes were **never** marked failed, silently breaking the existing `build_generation_workflow` chain too. The 3-arg signature only works for *unbound* errbacks.
- **Pattern:** a `link_error` errback that needs the exception must either be unbound, OR make `exc`/`traceback` optional and recover them from the result backend (`AsyncResult(task_id).result/.traceback`). Don't trust that a `.s(episode_id=...)`-style errback gets `(request, exc, traceback)` — prove it with a test that calls the errback the way Celery's old-style path does: `errback.run(task_id, **bound_kwargs)`.
- **Eager mode does NOT run `link_error`**, so an eager test can't catch this. Test the errback function directly with the old-style arg shape instead.
- **Verify-before-fix on a review finding:** codex's first claim ("link_error signature wrong") was initially doubted because the same pattern was already all over `build_generation_workflow` — but "already used" ≠ "works". Empirically reproducing the `TypeError` confirmed it was a real *latent* bug, not a regression I introduced.

## Wiring previously-dead enforcement code breaks tests that assumed it was dead (#297/PR #332)
- **2026-06-27:** `check_episode_limit`/`track_api_call` etc. had zero callers; wiring them in
  silently broke existing tests written under the dead-code assumption: `test_pagination_basic`
  (25 episodes for one **free** user → now 402 on the 6th) and `test_billing` asserting a new
  user's `api_calls == 0` (reading usage is now itself a metered call). **Pattern:** before
  activating dormant enforcement, grep tests for loops/asserts that depend on the *un*-enforced
  behavior. Fix at the fixture level when possible (seed an enterprise/unlimited sub on the shared
  `project_and_auth`) rather than editing each test.
- **conftest `override_get_db` rolled back the SHARED test session on ANY exception incl.
  `HTTPException`.** Production uses a session-per-request, so a 402/404 there never wipes other
  requests' data — but the test session is shared across all requests in a test, so the rollback
  nuked the registered user → FK violation on the next request. Fix: re-raise `HTTPException`
  without rolling back; only roll back on genuine (non-HTTP) errors.
- **Global metering on a deleted user → FK violation, not 401.** `billing_usage`'s only FK is
  `user_id`; a metering insert for a token whose user was deleted raises `IntegrityError`. Catch
  it, roll back, and let `get_current_user` return the real 401 — metering must not 500 or
  pre-empt auth. Also use `verify_access_token` (not `verify_jwt_token`) in the soft user-id
  helper so refresh/verification tokens aren't metered (auth returns 401, not a metering 402).
- **api_calls = request meter (count at boundary, all authed requests incl. failures);
  episodes_created = billing unit (track only after a successful create).** CodeRabbit suggested
  moving api-call tracking to a post-2xx hook — declined: that lets a client spam failing requests
  for free, defeating the abuse-prevention goal. Exempt `/billing/*` from the api-cap *gate* (still
  counted) so an over-quota user can still view usage and upgrade — otherwise the recovery path 402s.
- **`pytest.ini` `testpaths = tests tests/unit` makes bare `pytest` UNDER-collect (~half the
  modules, silently).** CI runs `pytest tests/` (explicit path) and collects everything, so the
  authoritative full run is `cd apps/api && uv run pytest tests/` (~1565 tests), NOT bare `pytest`
  (~727). The local persistent DB also accumulates cross-run cruft → the full local suite flakes
  (e.g. `test_audio_snippets::test_download_url_no_s3_config` fails on `main` too); CI's fresh
  ephemeral DB is the real gate. Don't chase wandering local-suite failures that don't reproduce
  on a clean DB / in CI.

## RLS fail-loud migration guard interacts with CI's least-privilege migration job (#301/PR #336)
- **2026-06-27:** Adding `SET LOCAL row_security = off` before the 006/012 backfills makes a
  non-BYPASSRLS migration run **error** (`query would be affected by row-level security policy`)
  instead of silently no-op'ing. That's the intended fix — but the existing CI job
  `migrate-as-non-superuser` (test.yml) ran `alembic upgrade head` as a plain NOSUPERUSER owner
  (no BYPASSRLS), so the guard would have turned that previously-green job RED. Before adding a
  fail-loud DB guard, grep CI/deploy for every place that runs migrations under a non-privileged
  role; that job's premise changes, not just the migration. Reframed it to the two-role model
  (positive: BYPASSRLS migration role succeeds; negative: non-BYPASSRLS fails loudly).
- **A negative CI test ("must fail") must assert the failure REASON, not just non-zero exit.**
  `if uv run alembic upgrade head; then exit 1; fi` goes green on *any* break (an unrelated 003
  GRANT error would satisfy it). Capture output and `grep -qi 'row-level security'` so the test
  actually proves the guard fired. (Self-caught mid-flight; CodeRabbit independently flagged it Major.)
- **A role attribute, not superuser, is the right lever:** `NOSUPERUSER NOCREATEDB NOCREATEROLE
  BYPASSRLS` keeps the "migrations need no elevated DDL privileges" guard intact while letting
  RLS-affected backfills see all rows. `FORCE ROW LEVEL SECURITY` makes even the table owner
  subject to RLS — owning the table is not enough.
- **Demo against a real DB, both directions:** spun up `postgres:16` in docker, provisioned the
  exact role matrix, ran `upgrade head` under a BYPASSRLS role (succeeded through 006/012) and a
  non-BYPASSRLS owner (failed with the precise RLS error). Outcome evidence, not "exit 0".

## A task entry-guard races the dispatcher's status commit (#295/PR #330)
- **2026-06-26:** Added an entry-time idempotency guard to `generate_podcast_task`
  (short-circuit if `generation_status == "complete"`). codex flagged a P1: the
  router dispatched the task **before** committing `generation_status="queued"`
  (it needed `task.id` from `apply_async` for `generation_progress`). A fast worker
  could read the stale `complete` status and skip a legitimate **regenerate**, then
  the router commits `queued` → episode stuck until the reaper. Adding a guard that
  reads a status the producer hasn't committed yet is a write-after-dispatch race.
- **Fix pattern:** pre-generate the id (`task_id = str(uuid4())`), commit the
  starting status **before** `apply_async(task_id=task_id, ...)`. Then a worker can
  never observe a pre-transition status. Order: persist intent → enqueue.
- **Reordering opens a new failure mode (two more codex P2s):** once you commit
  `queued` before enqueue, a broker-down `apply_async` leaves a committed `queued`
  with no task → wrap enqueue in try/except and **restore the prior status**, not a
  blanket `failed` — clobbering a still-`complete` episode makes its existing audio
  undownloadable (download endpoint gates on `complete`). Snapshot
  `prior_status`/`prior_progress` before overwriting; restore + 503 on enqueue error.
- **Celery retry vs. the guard:** with `acks_late=False`, `self.retry()` re-runs the
  same task_id but the status is now the in-progress value the guard would skip on.
  Make the Redis lock **re-entrant by task_id** and bypass the in-progress gate when
  `self.request.retries > 0`, else retries silently no-op. Release the lock on every
  *terminal* exit but NOT the retry path (TTL is the crash backstop).

## E2E test-trust (#302) — re-enabling fixme'd tests verifies the APP, not just selectors
- **A `fixme`'d E2E suite can hide a broken app, not just stale selectors.** Re-enabling
  #302's specs surfaced that core project/episode **creation is broken** (web sends
  `title`/`{language,explicit}`; backend `ProjectCreate` requires `name` +
  `podcast_metadata{show_title,author,description}`; `GET /projects` 500s). Filed #337.
  Lesson: when "fixing E2E selectors," actually RUN the flow against the deployed app
  early — the cheapest probe is a direct `curl` to the API contract before driving the UI.
- **Verify the web↔API contract by reading both schemas + the proxy.** `/api/proxy/[...path]`
  is a transparent pass-through (no field remapping), so frontend `title` vs backend `name`
  mismatches fail at runtime, never at build. Check `apps/api/src/schemas/*.py` field names
  against the web `fetch` body before trusting a flow.
- **Playwright `test.describe.fixme` ⇒ Playwright reports those as *skipped*, exit 0.** CI's
  `needs.test.result` check then prints "Tests passed!" → false green. Gate on a real signal:
  emit `['json',{outputFile}]` and fail when `stats.expected < MIN_PASSED` (an all-skipped
  suite has `expected: 0`). `stats.expected` = passed; `-g` filtered-out tests are excluded
  (not counted as skipped), but an unfiltered run counts `fixme` as `skipped`.
- **Dev registration is rate-limited (3/hr/IP).** For two-session isolation, provision a
  persistent second tenant once in `global-setup` (deterministic plus-addressed email,
  idempotent register) rather than `signUpAndLogin()` per test — fewer regs, more stable.
- **Shadcn/Radix dialog trap:** the open-trigger and the form submit often share a label
  ("Create Project"). Scope the submit to `getByRole('dialog').locator('button[type=submit]')`
  to avoid Playwright strict-mode ambiguity.

## Web↔API contract (#337/#340)
- **A "field mismatch" contract bug is usually more than field names.** #337 read as
  `title` vs `name`, but exploration also found: the list read a non-existent envelope key
  (`data.items` vs API's `{projects:[…]}`), a call to a route that doesn't exist
  (`/episodes/projects/{id}/episodes` vs real `GET /episodes?project_id=`), and PATCH where the
  API exposes PUT. When aligning a contract, verify envelope key + route path + HTTP method +
  field shape — grep the actual router decorators and the `response_model`, don't trust the
  frontend's assumed shape.
- **Partial JSONB updates must merge, not replace.** `setattr(obj, "episode_metadata", value)`
  overwrites the whole JSONB column, so a title-only edit silently drops description/format/
  explicit/tags. Shallow-merge `{**existing, **provided}` in the service update fn (fixes all
  callers) rather than making every caller resend the full object.
- **Relax create-time validation where the UI doesn't collect the field, but keep the
  completeness gate where it matters.** #337 dropped required show_title/author at *create*
  (UI collects neither) while leaving the *distribution-time* `REQUIRED_METADATA_FIELDS` gate
  intact — lightweight create, strict publish.

## 2026-07-05 (#302 tail, PR #344)
- **Verify reviewer claims empirically before fixing.** GLM's HIGH ("test passes for the wrong reason under the savepoint fixture") was disproven in 2 minutes by reverting the fix and watching the test fail. Plausible mechanism ≠ actual behavior.
- **`gh workflow run --ref <branch>` races a just-pushed commit.** It resolved the pre-push SHA once; always check the run's `headSha` against local HEAD before trusting a dispatch.
- **Persistent E2E users + hard billing quotas self-poison.** Shared tenants accumulate metered usage across runs (5 episodes/month burned in a day). Dev/staging needs an enforcement kill-switch (BILLING_ENFORCEMENT_ENABLED=false), same pattern as the rate-limit/email flags.
- **A "test-trust" issue can conceal a bug stack.** Five layers here (nginx try_files, /api/* ownership, RLS-vs-commit, web route prefix, quota exhaustion) — each invisible until the previous was fixed. Re-run E2E after every layer; don't assume one fix is THE fix.

## Removing "dead" INI sections can activate other dormant config (2026-07-07, PR #345)
pytest.ini had `markers` and `filterwarnings` written BELOW `[coverage:run]`/`[coverage:report]`
headers — INI parsing assigned them to those sections, so pytest never saw them. Deleting the
"dead" sections hoisted `filterwarnings = error` into `[pytest]`, activating it for the first
time and killing CI collection (pydub compile-time SyntaxWarning → SyntaxError, pytest exit 4).
Lesson: before deleting an INI/TOML section, check what the *parser* attributes to it — entries
after a section header belong to that section even if they visually look like part of an earlier
one. When cleaning dead config, diff the *effective parsed config* before/after, not just the text.
Also: it passed locally because pydub's .pyc was already compiled (SyntaxWarning only fires on
first compile); fresh CI venvs recompile. Clear __pycache__ to reproduce compile-time warnings.

## E2E/CI Postgres: never bootstrap the service as the app user when RLS is the product
- **2026-07-08 (#341):** First local PR-built-stack E2E run had the 3 isolation
  specs failing — User B could read User A's project. Root cause: the Postgres
  container's bootstrap user (`POSTGRES_USER: podcastfy`) is a **superuser**, and
  superusers bypass RLS even under `FORCE ROW LEVEL SECURITY`, so connecting the
  API as it silently disables multi-tenancy. Any stack that exercises tenant
  isolation must mirror the dev two-role model (#301): migrate as the BYPASSRLS
  owner (`podcastfy_user`), run the app as the RLS-subject `podcastfy_app`.
  `rm-review.yml` still uses the superuser-bootstrap pattern but only
  health-checks, so it survives; copy its services block, not its DB role.

## Local "full suite" wasn't: testpaths multi-entry silently under-collects
- **2026-07-09 (#346/PR #348):** `testpaths = tests tests/unit` in pytest.ini made
  bare `pytest` collect ONLY tests/unit — 767 of 1662 tests. CI passes `tests/`
  explicitly, so it ran ~900 tests my local verification never touched, and the
  newly-activated `filterwarnings=error` failed 24 of them (starlette deprecated
  status constants, leaked `asyncio.to_thread` coroutines from wait_for mocks).
  Lessons: (1) verify with **CI's exact invocation** (`pytest tests/`), not a bare
  `pytest`, before declaring the suite green; (2) sanity-check collected-test
  counts against CI's log — a big mismatch is config rot, not parallelism magic;
  (3) tests that patch `asyncio.wait_for` must `coro.close()` the coroutine arg
  or the never-awaited RuntimeWarning fires at GC inside an unrelated later test.

## 2026-07-10 (#309, PR #368)
- **Mutation testing must not use `git checkout --` to revert** when the file has
  uncommitted edits from a later fix round — it silently wipes them (had to
  re-apply the composed-path fix). Apply the mutation with a Python string-replace
  script and restore by re-running the same script inverted, or commit first.
- opencode post-PR reviews on full PR diffs can exceed a 10-min foreground
  timeout; run `ask-opencode.sh` in the background writing to a file, then post.

## 2026-07-10 (#310, PR #369)
- **`showboat` syntax gotchas:** it's `exec <file> <lang> [code]` (fork/exec, no
  shell — multi-line strings and `VAR=$(...)` fail without a `bash` lang arg), and
  `pop` removes the *most recent* entry, so repairing an earlier bad entry means
  popping everything after it too — count entries before popping.
- Issue plans can be stale by the time they're implemented: most of #310's plan
  (deprecated `utcnow()` replacement) was already shipped in #348. Re-verify each
  plan step against current code before implementing (only the TZ-aware filter
  param bug remained).

## 2026-07-10 (#311, PR #370)
- **Mock tests must not assert outcomes impossible under real semantics.** The
  rollback-failure test originally asserted the episode got marked failed after
  `rollback()` raised — MagicMock allows it, but a real SQLAlchemy session would
  keep raising `PendingRollbackError` on every op until a successful rollback.
  Model the state machine in the mock (second `get` raises too) and assert the
  degradation path, or the test breeds false confidence. (Caught by post-PR GLM.)
- `showboat exec` signature is `<file> <lang> [code]` — omitting the lang makes
  it treat the whole command string as argv[0] and fail with fork/exec noise.
- `pytest | tail && git commit && git push` commits on FAILING tests — the
  pipeline's exit code is tail's (0), not pytest's. Always `set -o pipefail`
  (or check pytest's status separately) before chaining a test run into
  commit/push. Cost: a broken push to a PR branch on #366.
- Tests on tables without RLS (e.g. storage_deletion_outbox) must scope
  assertions to the test's own tenant/keys, never assert global table
  emptiness/equality — any concurrent writer to the shared dev DB (demo
  agents, second pytest session) breaks them.

## Mutation checks vs uncommitted work (2026-07-12, #378)
`git checkout <file>` to revert a test mutation also wipes any uncommitted edits in that file.
When running mutation sanity checks, either commit pending work first or revert the mutation by
re-applying the exact inverse edit — never a whole-file checkout.

## 2026-07-14 (#320, PR #400) — observability

- **`logrotate -d` exits 0 on an unknown option.** A typo (`rotat 14`) prints
  `error: ... -- ignoring line` and returns **0**, so `set -e` cannot gate it and the
  retention window silently vanishes. Verified against logrotate 3.21: exit 1 only when the
  *log file is missing*, which masks the real signal. Must also grep output for `^error:`.
  Same family as the `redis-cli exits 0 on ERR` lesson — **never trust a CLI's exit status
  for config validation without checking what it prints.**
- **Unquoted `<< EOF` heredocs command-substitute backticks — including inside `#` comments.**
  Markdown-style comments (`` `pm2 install` ``) in a deploy heredoc *execute on the CI runner*
  and are stripped from what the server receives. Static tests never see it; render the heredoc
  through a stubbed `ssh` to catch it. All of deploy-dev.yml's SSH blocks are unquoted heredocs.
- **A module-global async engine + pytest-asyncio's per-test event loop = pooled connections
  crossing loops.** `/ready` using `src.database.engine` passed alone but poisoned the *next*
  test with "got Future attached to a different loop", because the pool cached a connection
  bound to a dead loop. Production is unaffected (uvicorn = one loop per process), so dispose
  the engine between tests rather than weakening the probe. Same root cause as the documented
  Celery `asyncio.run` pool trap.
- **An unhandled 500 escapes `BaseHTTPMiddleware` entirely.** Starlette's `ServerErrorMiddleware`
  sits *outside* user middleware, so a response-header-setting middleware never runs for a 500 —
  the response users most need a correlation id on was the only one without one. `request.state`
  (unlike a contextvar reset in `finally`) *does* survive into the 500 handler; stamp it there so
  the exception still reaches Sentry instead of being swallowed by the middleware.
- **opencode now stalls even on small diffs**: `zhipuai/glm-5-turbo` timed out at 10m on a full
  diff and again at 7m20s on a 536-line one. `codex review --base <branch>` worked both times
  and is the reliable fallback — but disclose which reviewer actually ran, since the repo rule
  names opencode as primary.
