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
  **The same trap bit again minutes later**, outside any deploy: `gh pr comment --body "...markdown
  with backticked `paths`..."` command-substituted the path, which executed and vanished from the
  posted comment. Any double-quoted shell arg carrying markdown must go through `--body-file` plus a
  quoted `<<'EOF'` heredoc. The rule is about double-quoted shell context generally, not heredocs.
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
- **FastAPI's `detail` has two shapes, and `response.json()` is `any`, so TypeScript cannot see
  the difference.** `HTTPException` gives a string; *every* Pydantic 422 gives an array of
  `{msg, loc, type}`. Assigning that array to `string` state and rendering it throws React error
  **#31** ("Objects are not valid as a React child"), and with no error boundary the whole route
  dies as the browser's *"This page couldn't load"* — which reads like a missing error message,
  not a crash (#481). Always go through `extractApiErrorDetail`. Note the two call sites that
  interpolated `${body.detail}` were both on `status === 422` branches and typed
  `{ detail: string }` — the type annotation asserted the one thing that is never true there.
- **A page-wide text regex in an E2E assertion can match the crash page.**
  `text=/error|already|exist/i` matched Next's own error screen, so the test passed when the app
  *crashed* and failed only when the crash surfaced differently — a false green that survived ~10
  runs and looked like flake. Assert a specific element (`#signup-error`), never page-wide prose.
  Measured directly: the old regex passed on the dead page and did not match the correct
  validation message.
- **Local E2E needs two things CI sets and `.env.example` does not.** `CORS_ORIGINS` must include
  the Playwright web origin (`["http://localhost:3200"]`, per `playwright-tests.yml`) or every
  browser `fetch` fails and the UI shows the generic catch-block message; and **port 5432 on this
  machine is squatted by a non-project Postgres** that answers with an auth failure rather than
  connection-refused — bind the demo container to 5433 and point both DB URLs at it.
- **`next build` rewrites `apps/web/tsconfig.json`** (`jsx: preserve` → `react-jsx`, plus a
  `.next/dev/types` include). Check `git status` after any local build so the churn does not ride
  into a PR. Related: deleting a component whose test imports it fails the build at the
  *type-check* step, not the compile step.
- **`coderabbit --prompt-only` no longer exists** — the flag is now `--agent` (with
  `--base <branch>` / `--committed`). The old invocation exits 0 after printing usage, so a review
  step wired to it silently does nothing while looking like it succeeded.
- **Local pytest silently targets the wrong Postgres on a machine where :5432 is taken.**
  `tests/conftest.py` defaults `TEST_DATABASE_URL` to
  `postgresql+asyncpg://podcastfy_app:podcastfy_app_password@localhost:5432/podcastfy`. If anything
  else owns 5432 the whole suite dies with `asyncpg.exceptions.InvalidPasswordError: password
  authentication failed for user "podcastfy_app"` -- 725 errors that look like a catastrophic code
  break and are purely environmental. Note the failure mode is an *auth* error, not
  connection-refused, so it reads like a credentials bug rather than "wrong server". Provision the
  container on another port and pass `TEST_DATABASE_URL=...@localhost:<port>/podcastfy` explicitly;
  the `podcastfy_app` role itself is created by migration `003_force_rls.py`, so no manual
  `CREATE ROLE` is needed.
- **A PR's green CI is computed on *its own base*, and goes stale when main moves.** #483 (ESLint
  flat config + eslint 8→10) sat green for two days on a base predating #484, whose new files had
  therefore never been linted under the config #483 introduces. Merging on that green is how a PR
  lands clean and turns `main` red on the next commit. For any repo-wide change — lint/format
  config, tsconfig, a shared type — merge the base branch in and re-run the *new* tooling over the
  *combined* tree before merging out. GitHub's "mergeable / no conflict" says nothing about this:
  the conflict is semantic, not textual.
- **`npm install` can rewrite `package-lock.json` without any dependency changing.** A local
  install stripped `libc` fields from optional platform packages (an npm-version difference), which
  would have ridden into a PR as unrelated churn. Check `git status` after any local install and
  revert a lockfile diff you did not intend.
- **ruff's `DTZ` family fights this codebase on purpose, so do not adopt it.** Model columns are
  `DateTime` *without* time zone and `src/utils/datetime_utils.py` deliberately returns naive UTC —
  "asyncpg rejects aware values for those columns" (#346). Of 25 DTZ findings tree-wide, 21 are in `tests/`; the rest are
  `services/rss_generation_service.py` (x2), `services/usage_service.py` and
  `scripts/check_credentials.py`.
  "Fixing" a naive datetime to be aware in code that writes to those columns breaks the insert at
  runtime, so adopting DTZ would mean ~24 `# noqa`s for zero safety gain. The helper itself passes
  DTZ cleanly, because `datetime.now(timezone.utc).replace(tzinfo=None)` is the right way to spell
  "deliberately naive UTC".
- **`BLE001` is 62 individual judgment calls (55 in `src/`, 7 in `scripts/`), not a sweep.** Several blind excepts are correct
  defensive code at a trust boundary — e.g. `src/middleware/auth.py:80` returns `None` on *any*
  token-verification failure, and narrowing it risks a 500 on an unanticipated malformed token.
  Adopting it needs a per-site review, which is why it was split out of #482 rather than bundled
  with the two unambiguous rules.

## #501 / PR #523 (2026-09-15) — S3 failure status + disclosure

- **`showboat exec` takes a language argument: `showboat exec <file> bash '<cmd>'`.** Without `bash`
  it `fork/exec`s the whole string as a binary and every step silently records nothing. Also
  export every variable the exec'd commands reference — showboat inherits the environment, not
  shell locals.
- **Do not wait on opencode/GLM for the cross-family review.** Third stall in a row (zero output
  at 420s on a ~200-line diff). Start `codex review --base main` in parallel from the outset;
  it returned in ~3 min. The memory note already said this; it was ignored and cost 7 minutes.
- **The auto-mode classifier refuses to commit an edit to `security-audit.sh`'s ignore list
  ("CI bypass").** That is the right instinct — extending the pip-audit ignore list is a policy
  call. Resolved structurally by #518 / PR #558: litellm advisories no longer need an entry at
  all; a new non-litellm advisory still needs a human-committed `TRIAGED` entry.
- **Local Postgres for the backend suite is gone with `api-postgres-1`.** An ephemeral
  `postgres:16` container with the `.env` credentials plus `alembic upgrade head` is a 90-second
  setup and runs the full 1917-test suite in ~3.5 min.

## #520 / PR #525 (2026-09-15) — dead `except MaxRetriesExceededError` branches

- **Celery task unit tests that do not patch `acquire_generation_lock` hit the real Redis.** Tests
  with fixed episode ids (`ep-gen-01`) left `podcast_generation_lock:*` keys behind; once an earlier
  file left a task id on the shared request context, `acquire()` saw a foreign owner and the task
  returned `_skipped_result(...)` — an order-dependent failure that only shows in the full suite.
  Patch `acquire_generation_lock`/`release_generation_lock` in unit tests, or use fresh uuids.
- **A "real Celery decides" exhaustion test usually passes against the OLD code too**, because
  `retry(exc=e)` already re-raised. The discriminating assertion is the *stranded side effect*
  (lock released, status written, log line emitted via `caplog`) — RED comes from those, not from
  `pytest.raises`. Mutation-check by replacing the terminal `raise` with a `return`.
- **A subagent running `git diff` can leave a stale zero-byte `.git/index.lock`** that blocks the
  orchestrator's commit; `pgrep -a git` empty + 0-byte lock = safe to `rm`. Retry once before
  removing.
- **`pkill -f "opencode run"` kills the shell that issued it** (its own command line matches).
  Kill by process name: `pkill opencode`.
- **opencode/GLM stalled for the fourth time** (zero output after 7 min on a 45 KB diff); codex
  returned in ~4 min twice. Stop launching opencode for reviews in this repo.
- **The `feature-dev:code-reviewer` subagent forked its own sub-reviewer** that messaged the
  orchestrator directly with a duplicate verdict. Tell reviewer subagents explicitly not to spawn.
- **Showboat grep evidence must anchor on the code form** (`except X:` with the colon); a
  comment describing the removed pattern matched the bare name and muddied "no handler remains".

## #489 / PR #528 (2026-09-16) — react-hooks 7 rule adoption

- **`react-hooks/set-state-in-effect` semantics (read from the plugin source, not the docs):** a setState is
  flagged when reachable through the effect body's own blocks — *including after `await`* and inside
  `if`/`try` — or through a component-level function that calls setState directly (`useCallback` is
  erased first, so async loaders count). setState inside a `.then` callback or a function declared
  inside the effect is not traced. Probe candidate shapes with a scratch `.tsx` and
  `npx eslint --rule '{...:"error"}' -f json` before designing the refactor.
- **An `incompatible-library` finding hides other findings in the same file** — the compiler skips the
  component entirely, so fixing `watch()` → `useWatch()` unmasked 2 more sites. Re-run the probe after
  each fix; the issue's count is a floor.
- **A render-time read of `window.location` misses client-side navigations.** During an App Router
  transition the new page renders before the browser URL updates, so a lazy `useState` initializer saw
  the *previous* page's URL. jest passed (it sets the URL before render); only the browser demo caught
  it. Read the router (`useSearchParams`) instead — every route here is dynamic (root layout reads
  `headers()`), so no Suspense boundary is needed.
- **"Loading" that used to be set at the top of a loader must become derived state once the loader
  moves into the effect** — key the loaded result by the id/period it belongs to and derive `loading`
  from the mismatch; otherwise App Router id reuse shows stale content (codex caught this).
- **`showboat exec` is `exec <file> bash '<cmd>'`** (no shell without the lang arg) and `showboat image`
  wants the echoed path relative to the cwd; it copies the file to a hashed name next to the doc, so
  delete the original afterwards and prune orphans after a `pop`.
- **Frontend diff-cover:** rewrite `SF:src/…` to `SF:apps/web/src/…` and run from the repo root, else
  "No lines with coverage information". `codex review --base main` takes no positional prompt.
- **`pkill -f "next start"` kills the shell that issued it** (self-match, again) — `fuser -k 3000/tcp`.
- **Background pollers (`gh pr checks --watch`, sleep loops) get killed under memory pressure** on this
  box (mongod holds ~2.7 GB); poll in the foreground with a bounded loop.
- **The GLM review check can pass with an empty placeholder comment** — green ≠ reviewed (#497).

## #490 / PR #531 (2026-09-16) — the "flaky" pagination test

- **A flake report without the traceback is folklore.** #490 recorded only "failed once in ~6 runs";
  the test's only failable assertions were two status codes, so the actual error was lost. When
  filing an intermittent, paste the `--tb=long` output (or `cp` the log) before anything else — the
  report from #486 also omitted that the machine was under memory pressure at the time.
- **Before chasing order dependence, check whether leaked rows could even reach the test.** Every user
  here is its own RLS tenant, so cross-test row leakage is structurally impossible for any list
  endpoint; and a test that asserts `len <= N` cannot fail on a leak or an unstable sort. Read the
  assertions first — they bound what the flake can be.
- **A background pytest loop reads the working tree.** Two "failures" in the 42-run loop were my own
  RED test running in the ~20 s window between editing the test and applying the fix. Either stop the
  loop before editing, or timestamp every failure against the file mtimes before believing it.
- **The `order_by(created_at.desc())`-with-no-tiebreak shape is repo-wide** (8 services, #530). Any
  new paginated list gets the PK as the final sort key; the `test_list_pagination_page_size` shape
  (force a tie via direct UPDATE on the shared session, page through, assert no dup/skip + order) is
  the template.
- **A subagent reviewer may not have Bash.** The internal reviewer confirmed diff scope via `grep`
  instead of `git diff`; it still found the #530 sweep. Give reviewers the file list in the prompt so
  a missing tool does not silently narrow the review.

## #491 / PR #532 — nginx CSP drift on the dev box, deploy-side drift gate

- **Auto mode denies remote writes over ssh** ("Remote Shell Writes" classifier), and the denial
  drops the *whole* Bash command — including read-only steps chained before it. Capture before-state
  evidence in its own command first, then hand the root commands to Frank with the exact lines.
- **Operator-installed config needs an operator-independent check.** Committing
  `deployment/nginx/podcastfy.conf` meant nothing for two months because nothing compared it to the
  box. Anything installed by hand as root gets a read-only runner-side assertion in the deploy
  (`check-nginx-drift.sh` is the template: `ssh cat` + `diff -u` against the committed file rendered
  with the same substitutions provisioning applies).
- **Put post-deploy gates after the health check, not before the deploy.** A drift in a root-owned
  asset should turn the run red, not hold a security bump hostage to a one-minute re-sync.
- **Do not bundle an nginx conf change into a PR that adds a drift gate**: the change re-drifts the
  box the moment it merges. The `ssl_stapling` cleanup went to #533 for exactly that reason.
- **Never put the box's address in demos or scripts** — a local `Host staging-ts` ssh alias keeps
  Showboat output and script logs clean (`~/.ssh/config`, Tailscale route).
- **Sibling-file style beats the linter's opinion when the linter does not own the directory**:
  `deployment/tests/` is tab-indented and outside `apps/api`'s ruff format scope; `ruff check` there is
  still useful (it caught `subprocess.run` without `check=`), `ruff format --check` is not.

## #493 / PR #535 (2026-09-17) — completing the abandoned #492 mutation pass

- **`showboat exec` is `<file> <lang> [code]`, not `<file> '<shell command>'`.** With one argument it
  execs that string as the interpreter and reads the code from stdin, so in a backgrounded shell it
  hangs forever with no child process and no output. Always `showboat exec demo.md bash '…'`.
- **Committing inside a git worktree needs `BEADS_DIR=<main-tree>/.beads`.** The beads pre-commit
  hook (`.git/hooks/pre-commit.legacy`) runs in every worktree, the SQLite DB is gitignored and only
  exists in the main tree, and the hook's "Failed to flush bd changes" aborts the commit. Point the
  env var at the main tree's `.beads` for the commit; nothing else needs it.
- **A symlinked `node_modules` in a worktree shows as untracked** — `.gitignore`'s `node_modules/`
  matches directories only. Harmless, but never `git add -A` in that tree; add explicit paths.
- **A mutation driver must run the baseline first.** "Any non-zero jest exit = KILLED" reports a
  false "all killed" on a suite that is already red or a jest that cannot start — the exact failure
  the tool exists to catch. Codex caught it; `mutation-check-492.mjs` now exits 2 on a red baseline.
- **Give a reviewer its own worktree when the demo rewrites source files.** The mutation demo edits
  and restores `src/` every few seconds; a reviewer reading the same tree can see a mutated file.
  A detached throwaway worktree in the scratchpad (`git worktree add … --detach`) is enough.
- **Commit (or stash) before a mutation check.** The check ends with `git checkout -- <file>`, which
  restores HEAD — on #502 that silently discarded an uncommitted review fix, and the "fix" commit
  landed with only the tests in it (caught by re-reading `git show --stat`; amended before push).
- **A mutation must still parse.** Deleting the only statement in an `if` leaves an empty block →
  `IndentationError` → the test "fails" and the mutation is scored KILLED for the wrong reason.
  Substitute `pass` instead of deleting the line, and `ast.parse` the file before running the test.
- **A fresh `apps/api` worktree needs `uv venv --python /usr/bin/python3.12` before `uv sync`.**
  With no `.python-version`, uv picks its newest interpreter (3.14); `levenshtein` (via podcastfy)
  has no 3.14 wheel and its sdist build fails on scikit-build-core metadata. Copy `.env` in too.
- **`pkill -f <pattern>` / `pgrep -f … | xargs kill` from a Bash tool call kills the tool's own
  shell** when the pattern appears in that shell's command line (exit 144, #503). Stop a server by
  port instead: `fuser -k 8018/tcp`. For a background watcher, just let it be stopped via its task.
- **This box's `gh` has no `--json` on `gh pr checks`.** A poll loop gated on it spins forever with
  no output. Parse the tab-separated plain output (`awk -F'\t' '{print $2}'`) and exit on any
  state that is not pending.
- **A local `uv lock --upgrade-package X` rewrites unrelated markers** (uv 0.9.30 vs Dependabot's
  uv reformatted the Sphinx block). For a single-package security bump, apply Dependabot's lock
  hunk verbatim (`gh pr diff N | git apply`) and confirm with `uv lock --check`.

## #518 / PR #558 (2026-09-18) — audit gate: litellm warns, reachability test is the control

- **Hand-emitted GitHub workflow commands must not contain a bare comma in a property.** The
  runner splits `::warning title=a, b::msg` properties on `,` before unescaping, so the title is
  truncated and the remainder silently dropped. `core.warning()` escapes this (`%2C`); a raw
  `print()` does not. Caught only by the internal reviewer; now guarded by a test.
- **Both cross-family reviewers can be down at once.** codex hit its usage quota and opencode
  stalled (180s, no bytes) in the same run. Start both in parallel from the outset and fall back to
  a Claude subagent reviewer immediately rather than serially retrying.
- **Showboat demos must not depend on files in /tmp.** A demo that passes `showboat verify` in
  session can still be unreproducible; write helper scripts inside the exec block (heredoc) and
  `rm` the temp file before verifying.

## #519 / PR #559 (2026-09-18) — duplicate chain-level errback

- **Kill a background worker by pidfile, not by pattern.** `pgrep -f`/`pkill -f` match the tool shell's own command line, and so does the `ps | grep '[c]elery …'` bracket trick whenever the *same* shell command also contains the pattern unbracketed (e.g. it started the worker a few lines earlier). Both killed the tool shell (exit 144). Start with `celery … worker --pidfile /tmp/x/worker.pid` and stop with `kill $(cat /tmp/x/worker.pid)`.
- **A real-worker demo must consume every queue the chain can hit, including `celery`.** `merge_audio_snippets` / `distribute_to_platform` fall through to the default queue (#560), so `-Q audio_processing,callbacks` silently strands the stage. Check with `celery_app.amqp.router.route({}, name)` first.
- **Chain-level `link_error` is appended to every member task** (`_chain.prepare_steps`); never add one to a chain whose stages already carry errbacks. In tests, a single errback is stored unwrapped, so iterate `maybe_list(sig.options["link_error"])` and rehydrate with `celery.signature()`.
- **Cross-family review can be entirely unavailable** (codex usage cap + opencode stall on the same day). Disclose it in the PR body's Known Limitations and let the internal reviewer read library source for the load-bearing claim.

## #522 / PR #561 (2026-09-18) — Node 24 via per-user nvm on the dev VPS

- **Never rebase a feature branch to pick up main — merge it.** The workflow forbids force-pushing
  the feature branch; `git merge origin/main` (after stashing the user's uncommitted
  `tasks/todo.md`) gets the same result without rewriting pushed history.
- **A mutation loop that reverts with `git checkout -- <file>` also reverts uncommitted real
  edits.** It silently discarded a just-written fix in deploy-dev.yml. Commit before every
  mutation pass, every time — not just the first.
- **`nvm install <bare major>` resolves the newest *remote* patch on every run**, so it needs
  nodejs.org to be reachable. Pair it with `|| nvm use` so an outage falls back to an installed
  version instead of failing the deploy. The demo is what surfaced this, not the tests.
- **Auto mode denies even read-only SSH to the VPS ("Production Reads").** When a plan needs
  box state or a one-time box change, hand the user a single `! ssh staging-ts '…'` command
  that captures the before-state and makes the change together — early, not after a failed deploy.
- **Make a new deploy precondition fail closed, before anything mutates.** The missing-nvm run
  failed before `npm install` and left the old frontend online. It was harmless, and it counted
  as real evidence for the failure path.
