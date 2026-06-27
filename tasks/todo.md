# Issue #296 — billing_usage unique constraint on (user_id, period_start)

## Problem
`_get_or_create_usage` does check-then-insert with no DB uniqueness backstop. Concurrent
same-month requests both insert → `scalar_one_or_none()` raises MultipleResultsFound (500),
counts split across rows. Increments are also non-atomic (lost updates).

## Plan (TDD)

### 1. Model — `src/models/billing_usage.py`
- Add `__table_args__ = (UniqueConstraint("user_id", "period_start", name="uq_billing_usage_user_period"),)`
- Keep existing `index=True` on `user_id`.

### 2. Migration — `alembic/versions/013_add_billing_usage_unique_constraint.py`
- `revision = "013"`, `down_revision = "012"` (bare numbers, matching repo convention).
- `upgrade()`: dedup existing rows per `(user_id, period_start)` (aggregate metric cols into one
  surviving row, delete rest) via `op.execute`, then
  `op.create_unique_constraint("uq_billing_usage_user_period", "billing_usage", ["user_id", "period_start"])`.
- `downgrade()`: drop the constraint.

### 3. Service — `src/services/usage_service.py`
- `_get_or_create_usage`: use `insert(BillingUsage).values(...).on_conflict_do_nothing(index_elements=["user_id","period_start"])`
  (postgresql dialect), then re-select and return the guaranteed row.
- `track_episode_creation` / `track_api_call`: after ensuring row exists, atomic
  `update(BillingUsage).where(...).values(col=BillingUsage.col + 1, updated_at=...)`. Drop Python-side `+=`.

### 4. Test — `tests/test_usage_concurrency.py`
- Independent sessions/engine per coroutine (test_db rolls back, can't model parallel commits).
- `asyncio.gather` N concurrent `track_episode_creation` for same `(user_id, period_start)`.
- Assert: exactly one row, counter == N, no MultipleResultsFound. Clean up committed rows.

## Notes
- Test DB is real PostgreSQL (asyncpg) → `on_conflict_do_nothing` works.
- billing_usage has no RLS policy → concurrency test needs no tenant context.
