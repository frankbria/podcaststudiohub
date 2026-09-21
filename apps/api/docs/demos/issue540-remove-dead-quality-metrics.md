# Issue #540 — removing the quality-metrics surface that could never return data

*2026-09-21T05:29:15Z*

This demo proves three things, each mapped to an acceptance criterion from issue #540:

1. **The endpoints could never return data.** Not "we grepped and think so" — the only module in the entire tree that writes the key they read is the calculator itself, and nothing imports the calculator.
2. **The surface is gone.** The same three HTTP requests that reached a live (auth-gated) handler on `main` now hit no route at all.
3. **The revive half is filed**, not silently dropped.

Everything below runs against two real trees: a worktree checked out at `main` (the "before") and this branch (the "after"). Both import the same virtualenv, so the only variable is the code.

## The two trees under test

`main` is checked out in a separate worktree so the "before" state is a real running application, not a memory of one.

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before && git log --oneline -1 && echo '--- and this branch: ---' && cd /home/frankbria/projects/podcaststudiohub && git log --oneline -1
```

```output
f681557 refactor(api): delete dead ScriptGenerationService and its tests (#539) (#567)
--- and this branch: ---
ea56d28 refactor(api): remove the unreachable quality-metrics surface (#540)
```

## AC #1 — "No endpoint returns a permanent empty result"

The three endpoints all gate on `episode.generation_progress["quality_metrics"]`. If nothing ever writes that key, every response is empty forever.

Rather than grep for the string, the script below parses the **AST** of every module under `src/` on `main` and collects the literal dict keys of every assignment to `generation_progress`, every `progress.update({...})`, and every `progress["key"] = ...`. That enumerates what the pipeline *can* write, mechanically.

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before/apps/api && python3 /home/frankbria/.claude/jobs/f2afff4f/tmp/keys.py
```

```output
src/routers/generation.py:
    ['celery_task_id', 'progress', 'stage']
src/services/quality_metrics_service.py:
    ['quality_metrics']
src/tasks/callbacks.py:
    ['completed_at', 'composed_at', 'composition', 'distribution', 'duration_seconds', 'error_message', 'failed_platforms', 'status', 'upload', 'uploaded_at']
src/tasks/podcast_generation.py:
    ['error_message', 'progress', 'stage', 'status']

UNION of every key the pipeline can write (14):
    ['celery_task_id', 'completed_at', 'composed_at', 'composition', 'distribution', 'duration_seconds', 'error_message', 'failed_platforms', 'progress', 'quality_metrics', 'stage', 'status', 'upload', 'uploaded_at']

modules that write the "quality_metrics" key: ['src/services/quality_metrics_service.py']
```

So exactly one module writes the key: `quality_metrics_service.py` — the calculator itself. That closes the loop **only if nothing calls the calculator**. On `main`, nothing does, outside its own test file:

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before && grep -rn 'quality_metrics_service\|QualityMetricsCalculator' apps/api/src apps/web/src tests deployment docs .github alembic 2>/dev/null | grep -v 'src/services/quality_metrics_service.py:' || echo 'NO importer anywhere outside the module itself'
```

```output
NO importer anywhere outside the module itself
```

The chain is closed: the only writer of the key is a module nothing calls, so on `main` **no episode could ever have a non-empty `quality_metrics`** — every one of the three endpoints returned empty or 404 for every episode, permanently.

Two independent confirmations of the same conclusion:

- The transcript the calculator parses is gone too. It defaults to `data/transcripts/{episode_id}.xml`, but since #309 the engine writes into a per-run temp dir that is deleted after upload, and the pipeline hard-codes `transcript_path: None`:

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before/apps/api && grep -n 'transcript_path": None' src/tasks/podcast_generation.py && grep -n 'data/transcripts' src/services/quality_metrics_service.py
```

```output
64:        "transcript_path": None,
290:            "transcript_path": None,  # engine transcript is a temp artifact (#309)
433:            "transcript_path": None,
583:            "transcript_path": None,
106:			transcript_path: Optional explicit transcript path, defaults to data/transcripts/{episode_id}.xml
118:			transcript_path = f"data/transcripts/{episode_id}.xml"
```

- Even a hypothetical write would not have survived. Regenerating an episode **replaces** `generation_progress` wholesale rather than merging into it, so any stored metrics would be discarded on the next run:

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before/apps/api && sed -n '367,373p' src/routers/generation.py
```

```output
    episode.generation_status = "queued"
    episode.task_started_at = datetime.now(timezone.utc)
    episode.generation_progress = {
        "stage": "queued",
        "progress": 0,
        "celery_task_id": new_task_id,
    }
```

## AC #2 — the surface is gone from the running app

The probe below boots the **real ASGI app** in-process and issues the three GET requests over `httpx.ASGITransport` — no mocks, no test client stubs. The status code is the discriminator:

- **401 `Not authenticated`** means the route exists and the auth dependency ran.
- **404 `Endpoint not found`** means the router has no such path at all.

First, `main`:

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before/apps/api && PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /home/frankbria/.claude/jobs/f2afff4f/tmp/probe.py 2>/dev/null
```

```output
OpenAPI paths advertised: 64
quality-metrics paths advertised: ["/quality-metrics/episodes/{episode_id}", "/quality-metrics/projects/{project_id}", "/quality-metrics/projects/{project_id}/episodes"]

GET /quality-metrics/episodes/11111111-1111-1111-1111-111111111111
  -> 401 {"detail":"Not authenticated"}   [route EXISTS]
GET /quality-metrics/projects/22222222-2222-2222-2222-222222222222
  -> 401 {"detail":"Not authenticated"}   [route EXISTS]
GET /quality-metrics/projects/22222222-2222-2222-2222-222222222222/episodes
  -> 401 {"detail":"Not authenticated"}   [route EXISTS]
```

Three routes advertised, all reachable. Now the identical probe on this branch:

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /home/frankbria/.claude/jobs/f2afff4f/tmp/probe.py 2>/dev/null
```

```output
OpenAPI paths advertised: 61
quality-metrics paths advertised: []

GET /quality-metrics/episodes/11111111-1111-1111-1111-111111111111
  -> 404 {"detail":"Endpoint not found"}   [route GONE]
GET /quality-metrics/projects/22222222-2222-2222-2222-222222222222
  -> 404 {"detail":"Endpoint not found"}   [route GONE]
GET /quality-metrics/projects/22222222-2222-2222-2222-222222222222/episodes
  -> 404 {"detail":"Endpoint not found"}   [route GONE]
```

64 paths → 61, the three quality paths gone from the advertised schema, and all three requests now fall through to the application 404 handler. The app boots cleanly with the router unregistered, which is the other half of this criterion.

## Nothing dangling

A removal is only safe if no reference survives. Searched across the API, the web app, e2e tests, deployment configs, docs, CI workflows and migrations:

```bash
cd /home/frankbria/projects/podcaststudiohub && grep -rnE 'quality_score_service|quality_metrics_service|schemas\.quality_metrics|QualityScoreService|QualityMetricsCalculator|_rating_from_score|quality-metrics' apps/api/src apps/web/src tests deployment docs .github alembic 2>/dev/null || echo 'NONE — no surviving reference in any of: apps/api/src apps/web/src tests deployment docs .github alembic'
```

```output
NONE — no surviving reference in any of: apps/api/src apps/web/src tests deployment docs .github alembic
```

## The suite, unchanged except for the deleted tests

The delta must be **exactly** the tests that covered the deleted code — anything else would mean the removal broke something.

```bash
cd /home/frankbria/.claude/jobs/f2afff4f/tmp/main-before/apps/api && /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python -m pytest tests/test_quality_metrics.py tests/test_quality_metrics_endpoint.py tests/unit/test_quality_score_service.py --collect-only -q -p no:cacheprovider --no-cov 2>&1 | tail -2
```

```output

[32m========================= [32m97 tests collected[0m[32m in 0.04s[0m[32m ==========================[0m
```

97 tests collected on `main` in exactly those three files — which accounts for the entire suite delta of **1899 → 1802**, with **0 failures** on both sides. No other test changed behaviour.

Baseline (on `main`, before any edit) and the run on this branch:

| | `main` | this branch |
|---|---|---|
| passed | 1899 | 1802 |
| skipped | 7 | 7 |
| **failed** | **0** | **0** |
| coverage | 94.93% | 94.74% |

The coverage dip is arithmetic, not a regression: the removed modules were 100% / 100% / 95.9% / 97.7% covered, so deleting them removes more covered lines than uncovered ones. The gate is 85%.

```bash
echo 'main (baseline run, captured before any edit):' && sed 's/\x1b\[[0-9;]*m//g' /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/f2afff4f-609f-4c91-81b4-b46d210089c7/tasks/bhaqd7zhn.output | grep -E 'passed|Total coverage' | tail -2
```

```output
main (baseline run, captured before any edit):
Required test coverage of 85% reached. Total coverage: 94.93%
================= 1899 passed, 7 skipped in 218.24s (0:03:38) ==================
```

And the same suite on this branch, run live:

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && uv run --no-sync pytest tests/ -q -p no:randomly 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'passed|Total coverage' | tail -2
```

```output
Required test coverage of 85% reached. Total coverage: 94.74%
================= 1802 passed, 7 skipped in 197.84s (0:03:17) ==================
```

## AC #3 — the revive half is filed, not dropped

Issue #540 has five done-when boxes. Two of them — a generated episode carrying non-empty `quality_metrics`, and tests that assert the **pipeline** writes them — depend on #541 (P2.18) persisting a transcript and returning structured turns. They cannot be satisfied here, so they move to a tracked follow-up rather than being quietly checked off:

```bash
cd /home/frankbria/projects/podcaststudiohub && gh issue view 570 --json number,title,labels --jq '"#\(.number) \(.title)\nlabels: \(.labels|map(.name)|join(", "))"'
```

```output
#570 [P2.21] Revive quality metrics on the new engine: compute from structured turns and write them in the generation chain
labels: priority-p2, area-generation, area-quality
```

The follow-up records the exact `git show ea56d28^:…` commands to recover `QualityScoreService`, so deleting the scoring logic costs one command rather than a rewrite — and it states plainly that the XML parser must **not** come back.

## Evidence summary

| Acceptance criterion | Action | Outcome evidence | Status |
|---|---|---|---|
| No endpoint returns a permanent empty result | AST-parsed every `generation_progress` write on `main`; searched for importers of the sole writer | The only module writing `quality_metrics` is `quality_metrics_service.py`, which nothing imports → no episode could ever hold the key. Endpoints removed, not 501'd. | **VERIFIED** |
| App starts, no `/quality-metrics` route | Booted the real ASGI app on both trees and issued the same 3 GETs | `main`: 64 paths, 3 advertised, all **401 Not authenticated** (route exists). Branch: 61 paths, **0** advertised, all **404 Endpoint not found** (route gone). | **VERIFIED** |
| Nothing dangling | Searched `apps/api/src apps/web/src tests deployment docs .github alembic` | No surviving reference to any removed module, class, or the route prefix. | **VERIFIED** |
| Suite delta is only the deleted tests | Collected the three deleted files on `main`; ran the full suite on both trees | 97 tests collected = the exact 1899 → 1802 delta. **0 failures** on both sides. Coverage 94.93% → 94.74%, gate 85%. | **VERIFIED** |
| Revive half tracked | Filed the follow-up | #570 `[P2.21]`, blocked on #541, carrying the two deferred done-when boxes and the recovery commands. | **VERIFIED** |

## What this PR deliberately does not do

- It does not revive the feature — that needs #541 first.
- It does not touch `Episode.transcript_path` (the column), which is still read by `offboarding_service.py` and `episode_service.py`.
- It leaves one unrelated piece of rot found while verifying — `episode_service.py:459 update_generation_status`, which has zero callers and assigns a caller-supplied dict straight into `generation_progress`. Filed as #571 rather than widening this diff.

> Correction: I also filed the tracked sample transcripts as dead weight (#572) and closed it after checking. They live at repo root `data/transcripts/`, not under `apps/api/`; `.gitignore` documents keeping the already-committed samples on purpose; and podcastfy still creates that directory at runtime. The grep that misled me printed paths relative to its own cwd.
