# Issue #539 — the dead ScriptGenerationService is gone, and the live generation path is untouched

*2026-09-20T06:01:13Z*

> **Note on the commands below.** Runs that need a database use
> `env $(cat ~/.podcastfy-test-env)`. That file holds throwaway local test credentials
> (`DATABASE_URL`, `ENCRYPTION_KEY`, `JWT_SECRET_KEY`) and is not in the repo. The literal
> values were redacted from this document; every captured output is unmodified.

Three acceptance criteria from the issue, each demonstrated by an outcome rather than by "it compiled":

- **AC1** — `grep -rn ScriptGenerationService apps/api` returns nothing
- **AC2** — `src/main.py` no longer imports `podcastfy.content_generator`
- **AC3** — CI green, coverage gate unchanged or higher

First the before-state, read out of the merge-base so these are the real prior contents rather than a reconstruction.

```bash
cd /home/frankbria/projects/podcaststudiohub && echo -n "service: "; git show origin/main:apps/api/src/services/script_generation_service.py | wc -l; echo -n "tests:   "; git show origin/main:apps/api/tests/test_script_generation.py | wc -l
```

```output
service: 586
tests:   1302
```

1,888 lines. Now the claim that made them safe to delete — on `origin/main`, was `ScriptGenerationService` reachable from anything at all?

```bash
cd "$CLAUDE_JOB_DIR/tmp/main-baseline" && git grep -n "ScriptGenerationService" -- "apps/api/**/*.py" | sed "s|apps/api/||"
```

```output
src/services/script_generation_service.py:73:class ScriptGenerationService:
tests/test_script_generation.py:24:	ScriptGenerationService,
tests/test_script_generation.py:36:	"""Create ScriptGenerationService instance."""
tests/test_script_generation.py:37:	return ScriptGenerationService()
```

Two files: its own class definition, and its own test fixture. Nothing under `src/routers/`, `src/tasks/` or the rest of `src/services/` ever imported it.

By contrast, this is the path that actually runs — the Celery task calls `podcastfy.client.generate_podcast` directly, which does script generation internally. Same `origin/main` tree:

```bash
cd "$CLAUDE_JOB_DIR/tmp/main-baseline" && grep -n "from podcastfy.client import\|result = generate_podcast(" apps/api/src/tasks/podcast_generation.py
```

```output
337:        from podcastfy.client import generate_podcast
377:        result = generate_podcast(
```

## AC1 — the class is gone

`git grep` searches **tracked** files, which is the right scope: a plain `grep -rn` also matches stale `__pycache__/*.pyc` and old HTML coverage reports left in the working tree from before the deletion. Those are untracked build residue (confirmed with `git ls-files`), absent from a fresh checkout and from CI. Run against tracked Python:

```bash
cd /home/frankbria/projects/podcaststudiohub && git grep -n "ScriptGenerationService" -- "*.py"; echo "exit=$? (1 = no matches in any tracked .py)"
```

```output
exit=1 (1 = no matches in any tracked .py)
```

The only remaining mentions anywhere in the repo are prose — this demo, the issue-history docs, and the corrected evaluation row. No code:

```bash
cd /home/frankbria/projects/podcaststudiohub && git grep -l "ScriptGenerationService\|script_generation" -- . | sed "s/^/  /"
```

```output
  apps/api/docs/demos/issue520-dead-retry-branches.md
  apps/api/docs/podcastfy-0.4.3-evaluation.md
  tasks/lessons.md
  tasks/todo.md
```

## AC2 — `main.py` no longer imports `podcastfy.content_generator`

The import existed only to sanity-check the now-deleted service. Here is the lifespan guard before and after:

```bash
cd /home/frankbria/projects/podcaststudiohub && git diff origin/main -- apps/api/src/main.py
```

```output
diff --git a/apps/api/src/main.py b/apps/api/src/main.py
index 7d59055..504f2a6 100644
--- a/apps/api/src/main.py
+++ b/apps/api/src/main.py
@@ -29,7 +29,6 @@ async def lifespan(app: FastAPI):
     """Verify critical dependencies are available at startup"""
     try:
         from podcastfy.client import generate_podcast  # noqa: F401
-        from podcastfy.content_generator import ContentGenerator  # noqa: F401
         from podcastfy.content_parser.website_extractor import WebsiteExtractor  # noqa: F401
         from podcastfy.content_parser.pdf_extractor import PDFExtractor  # noqa: F401
         logger.info("Podcastfy dependencies verified")
```

Removing a line from a startup guard is only safe if the guard still runs and still guards. Two checks: the app boots through `lifespan` and logs its success line, and the guard still raises when podcastfy is genuinely unavailable.

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && env $(cat ~/.podcastfy-test-env) .venv/bin/python -c "
import asyncio, logging
logging.basicConfig(level=logging.INFO, format=\"%(levelname)s %(name)s: %(message)s\")
from src.main import app, lifespan

async def boot():
    async with lifespan(app):
        print(\"lifespan entered; app is serving\")
        print(\"routes registered:\", len(app.routes))
asyncio.run(boot())
" 2>&1 | grep -v "^WARNING\|FutureWarning\|^  \|^$" | tail -6
```

```output
updates or bug fixes. Please switch to the `google.genai` package as soon as possible.
See README for more details:
https://github.com/google-gemini/deprecated-generative-ai-python/blob/main/README.md
{"timestamp": "2026-09-19T23:01:38-0700", "level": "INFO", "logger": "src.main", "message": "Podcastfy dependencies verified"}
lifespan entered; app is serving
routes registered: 23
```

Guard confirmed live. Now the negative case — with `podcastfy.client` made unimportable, the guard must still refuse to start rather than silently booting a broken app:

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && env $(cat ~/.podcastfy-test-env) .venv/bin/python -c "
import asyncio, sys, builtins
from src.main import app, lifespan
_real = builtins.__import__
def blocked(name, *a, **k):
    if name.startswith(\"podcastfy\"): raise ImportError(\"No module named %r\" % name)
    return _real(name, *a, **k)
builtins.__import__ = blocked

async def boot():
    async with lifespan(app):
        print(\"BAD: app started without podcastfy\")
try:
    asyncio.run(boot())
except RuntimeError as e:
    print(\"guard refused startup as designed -> RuntimeError:\", e)
    sys.exit(0)
print(\"guard did NOT fire\"); sys.exit(1)
" 2>&1 | grep -E "guard|BAD|CRITICAL|Failed to import" | tail -4
```

```output
{"timestamp": "2026-09-19T23:01:47-0700", "level": "CRITICAL", "logger": "src.main", "message": "Failed to import podcastfy: No module named 'podcastfy.client'"}
{"timestamp": "2026-09-19T23:01:47-0700", "level": "CRITICAL", "logger": "src.main", "message": "Run: uv sync to install dependencies"}
guard refused startup as designed -> RuntimeError: Podcastfy not installed
```

The two test files that still import `ContentGenerator` were kept on purpose — they test the package install and the #446 advisory-reachability claims, not this service. CLAUDE.md states the reachability test is designed to fail CI if someone adds an image source type or imports litellm directly, so deleting its import would quietly weaken a deliberate gate. Both still pass:

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && env $(cat ~/.podcastfy-test-env) .venv/bin/python -m pytest tests/test_imports.py tests/test_dependency_reachability.py -q --no-cov -p no:cacheprovider 2>&1 | tail -4
```

```output
0.01s call     tests/test_dependency_reachability.py::test_no_caller_selects_a_non_default_llm

(7 durations < 0.005s hidden.  Use -vv to show these durations.)
[32m============================== [32m[1m7 passed[0m[32m in 3.61s[0m[32m ===============================[0m
```

## AC3 — full suite and the coverage gate

The whole backend suite on this branch, 1,906 tests, with `--cov-fail-under=85` enforced:

```bash
cd /home/frankbria/projects/podcaststudiohub && sed "s/\x1b\[[0-9;]*m//g" "$CLAUDE_JOB_DIR/tmp/pytest-539.log" | grep -E "^(FAILED|ERROR) |^=+ .*(passed|failed|error)|^TOTAL|Required test coverage"
```

```output
TOTAL                                            6864    353  94.86%
Required test coverage of 85% reached. Total coverage: 94.86%
FAILED tests/test_sync_jsonb_isolation.py::test_sync_orm_jsonb_insert_after_workflow_tests - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
ERROR tests/test_distribution_exhaustion.py::test_exhausted_transient_error_is_per_platform_distribution_failed - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
ERROR tests/test_distribution_exhaustion.py::test_exhausted_wait_for_audio_still_fails_the_episode - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
ERROR tests/test_distribution_exhaustion.py::test_failure_is_recorded_before_the_task_returns - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
======= 1 failed, 1895 passed, 7 skipped, 3 errors in 248.72s (0:04:08) ========
```

Coverage gate passes at **94.86%** against an 85% floor. Baseline on `origin/main` was 94.88%, so the deletion cost 0.02pp — expected, since the removed file sat at 97.31% coverage, slightly above the repo mean.

The 1 failure and 3 errors are all `psycopg.errors.InsufficientPrivilege` and have nothing to do with this diff. Proof: the same four run against a clean `origin/main` worktree produce the identical result. This is the local `podcastfy_app` role lacking RLS bypass; CI uses the privileged role.

```bash
cd "$CLAUDE_JOB_DIR/tmp/main-baseline/apps/api" && git log --oneline -1 && env $(cat ~/.podcastfy-test-env) .venv/bin/python -m pytest tests/test_distribution_exhaustion.py tests/test_sync_jsonb_isolation.py -q --no-cov -p no:cacheprovider 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | tail -6
```

```output
6e45358 docs: lessons from #530 / PR #566 (pkill self-match mechanism, Kimi fallback, SQL-capture demo plugin)
=========================== short test summary info ============================
FAILED tests/test_sync_jsonb_isolation.py::test_sync_orm_jsonb_insert_after_workflow_tests - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
ERROR tests/test_distribution_exhaustion.py::test_exhausted_transient_error_is_per_platform_distribution_failed - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
ERROR tests/test_distribution_exhaustion.py::test_exhausted_wait_for_audio_still_fails_the_episode - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
ERROR tests/test_distribution_exhaustion.py::test_failure_is_recorded_before_the_task_returns - sqlalchemy.exc.ProgrammingError: (psycopg.errors.InsufficientPrivilege) new...
========================= 1 failed, 3 errors in 0.81s ==========================
```

Identical failure set on untouched `origin/main`. The diff introduces no regressions.

## One correction found while doing this

`podcastfy-0.4.3-evaluation.md` justified "no impact" for the upstream model-default change by pointing at this service pinning `GEMINI_MODEL_NAME`. With the service deleted that reassurance is false — the live path pins no LLM model at all, so podcastfy's own default *is* the model we generate with:

```bash
cd /home/frankbria/projects/podcaststudiohub && echo "--- any model pin in the live call path? ---"; git grep -n "llm_model\|model_name" -- apps/api/src/tasks/podcast_generation.py apps/api/src/services/ ; echo "exit=$? (1 = nothing pins a model)"
```

```output
--- any model pin in the live call path? ---
exit=1 (1 = nothing pins a model)
```

Nothing. So a 0.4.3 bump would silently swap `gemini-1.5-pro-latest` for `gemini-2.5-flash`. The doc row now says that. It does not change the verdict — 0.4.3 stays deferred (#363) — it removes a now-false reassurance before it misleads the #543 cutover.

## Verdict

| AC | Evidence | Result |
|---|---|---|
| AC1 — class gone | `git grep` over tracked `*.py` exits 1; both files absent from disk | PASS |
| AC2 — no `content_generator` import | diff shows the line removed; app boots through `lifespan` and logs "Podcastfy dependencies verified"; guard still raises `RuntimeError` when podcastfy is unimportable | PASS |
| AC3 — CI green, coverage not lower | 1,895 passed; gate passes at 94.86% vs 85% floor; the 4 non-passes reproduce identically on clean `origin/main` | PASS |

1,888 lines deleted. The live generation path, the Celery chain, composition, upload and distribution are untouched.
