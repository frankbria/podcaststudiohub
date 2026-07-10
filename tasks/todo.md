# Issue #311 — Rollback before cleanup write in finalize_episode_generation_task

**Problem:** When the outer try in `finalize_episode_generation_task` fails on a DB error,
the session is left in a failed-transaction state. The `MaxRetriesExceededError` handler
(apps/api/src/tasks/podcast_generation.py:708-725) reuses that same session to mark the
episode failed; `db.get(...)` raises `InvalidRequestError`, the inner except logs it, and
the episode is stuck in an intermediate status.

**Decision (no fork):** `db.rollback()` on the existing session (CodeRabbit design choice 1;
matches service-layer rollback precedent).

## Steps

- [ ] RED: add tests in `apps/api/tests/unit/test_task_retry.py`
  - broken-tx cleanup: first `db.get` raises, retries exhausted → assert `rollback()` called
    before cleanup `get`, episode marked `failed`, cleanup `commit()` invoked
  - graceful degradation: cleanup commit also fails → returns `{"status": "failed", ...}` without raising
- [ ] GREEN: defensive `db.rollback()` (own try/except, log-and-continue) at start of the
  `except self.MaxRetriesExceededError:` block, before `db.get(...)`
- [ ] Quality gate: pytest, ruff, opencode review (pre-PR)
- [ ] PR, post-PR opencode review comment, demo (Showboat, API-only), CI green, merge
