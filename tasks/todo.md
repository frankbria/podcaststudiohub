# Issue #311 — Rollback before cleanup write in finalize_episode_generation_task

**Problem:** When the outer try in `finalize_episode_generation_task` fails on a DB error,
the session is left in a failed-transaction state. The `MaxRetriesExceededError` handler
(apps/api/src/tasks/podcast_generation.py:708-725) reuses that same session to mark the
episode failed; `db.get(...)` raises `InvalidRequestError`, the inner except logs it, and
the episode is stuck in an intermediate status.

**Decision (no fork):** `db.rollback()` on the existing session (CodeRabbit design choice 1;
matches service-layer rollback precedent).

## Steps

- [x] RED: ordering test failed on unfixed code (`['__enter__','get','get','commit','__exit__']` — no rollback)
- [x] GREEN: defensive `db.rollback()` at start of the `MaxRetriesExceededError` handler
- [x] GLM pre-PR review: APPROVE; took its Minor (cover rollback-failure branch → 3rd test)
- [x] GLM post-PR review: APPROVE; took its Minor (rework 3rd test to faithful SQLAlchemy
      semantics — cleanup get raises `PendingRollbackError` after failed rollback) + 2 nits
- [x] SHIPPED via PR #370 — 1703 passed + coverage gate, CI review bots "no defects" (both
      commits), real-Postgres demo posted to PR, CI green, squash-merged, issue #311 closed.
      Sibling-handler sweep: anti-pattern unique to finalize (others use fresh-session
      `_update_episode` or no DB).
