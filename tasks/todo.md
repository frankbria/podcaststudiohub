# Issue #295 — Idempotency guard for generate_podcast_task (P0.5)

**Problem:** `generate_podcast_task` runs under at-least-once delivery
(`task_acks_late=True` + `task_reject_on_worker_lost=True`) with no entry-time
idempotency check. Abrupt worker loss (OOM, deploy, SIGKILL) re-queues and
re-runs the entire **paid** LLM/TTS pipeline → duplicate billing + duplicate
artifacts.

**Dependency:** P0.4 (#294 terminal-status handling) — already merged.

## Adapted plan (verified against current code)

### 1. Fail-fast the expensive root task — `worker.py` untouched
- On `@celery_app.task(... name="generate_podcast")` decorator
  (`podcast_generation.py:103`), add `acks_late=False, reject_on_worker_lost=False`
  with a comment: paid, non-idempotent work must not be broker-redelivered.
- Leave global `worker.py:47-48` settings as-is (downstream tasks stay at-least-once).

### 2. New `apps/api/src/tasks/idempotency.py` — Redis episode lock
- `_redis()` → `Redis.from_url(settings.REDIS_URL, decode_responses=True)`
  (mirrors `distribution_target_service.py` / `rate_limiter.py`).
- `acquire_generation_lock(episode_id, task_id)`: `SET NX EX` with
  `ttl = CELERY_TASK_TIME_LIMIT + 60`, key `podcast_generation_lock:{episode_id}`,
  value `task_id`. **Re-entrant**: if key already holds *our* task_id (a Celery
  retry keeps the same id), return True. Fail-open (return True) on Redis error.
- `release_generation_lock(episode_id, task_id)`: atomic compare-and-delete via
  Lua eval (only deletes if we still own it). Fail-open on error.

### 3. Entry guard in `generate_podcast_task` (top of `try`, before podcastfy import)
- `_load_generation_status(episode_id)` helper (patchable; fail-open → None).
- `status == "complete"` → return early "already complete" (no chain, no paid work).
- `status` in active in-progress set
  {extracting,generating,synthesizing,uploading,composing,distributing} **and not
  a retry** → short-circuit as duplicate.
- queued / failed / draft / unknown(None) → proceed.
- `acquire_generation_lock(...)`; if not acquired → short-circuit (concurrent duplicate).
- Persist `generation_status="generating"` via existing `_update_episode`.

### 4. Release lock on every terminal exit (lock-held paths only)
- success return (`:354`), workflow-skip return (`:300`), soft-timeout return
  (`:382`), max-retries-exhausted return (`:433`).
- **Not** on the `self.retry()` path — same task_id re-runs and re-owns the lock;
  TTL is the crash backstop.

### 5. Tests — `tests/unit/test_generation_idempotency.py`
- acquire: first True / second-other-task False / re-entrant same-task True / fail-open True.
- release: compare-and-delete (owner only).
- task entry: complete → early return + podcastfy NOT called; in-progress dup →
  short-circuit; lock-held → short-circuit; queued → proceeds.
- decorator carries `acks_late=False` / `reject_on_worker_lost=False`.

## Acceptance criteria mapping
- [ ] complete/in-progress short-circuit before paid `generate_podcast(...)`
- [ ] only proceeds from queued/failed (unknown fail-open; retries re-own)
- [ ] Redis lock blocks concurrent/duplicate in-flight runs, self-heals via TTL
- [ ] `acks_late=False` so abrupt loss surfaces as failure, not a re-run
