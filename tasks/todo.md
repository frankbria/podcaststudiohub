# #318 — Migration safety: dupe-safe 006, lock-safe DDL, complete env.py metadata

Branch: `fix/318-migration-safety`

## Context
- All migrations ≤017 are already applied on every live env (staging VPS, CI runs fresh).
  Edits to historical migrations only affect fresh/behind DBs — but the fixes below are
  correctness/safety hardening that costs nothing and protects any future replay.
- env.py bug is LIVE: `target_metadata` only sees the original 11 models, so the next
  `alembic revision --autogenerate` would emit DROP TABLE for teams/billing/analytics/outbox.

## Changes

### 1. 006 — renumber pre-existing duplicates before constraint (correctness)
Before the NULL backfill, renumber duplicate (project_id, episode_number) non-NULL rows:
keep the earliest `created_at` per group, move later rows to `project_max + n`. Then the
existing NULL backfill and the unique constraint can never abort.

### 2. 006 — lock-safe NOT NULL + unique (acceptance: NOT VALID→VALIDATE, CONCURRENTLY)
- NOT NULL: `ADD CONSTRAINT ... CHECK (episode_number IS NOT NULL) NOT VALID` →
  `VALIDATE CONSTRAINT` → `SET NOT NULL` (PG12+ skips the scan via the valid check) → drop check.
- Unique: `CREATE UNIQUE INDEX CONCURRENTLY` in an `autocommit_block()`, then
  `ALTER TABLE ... ADD CONSTRAINT uq_episodes_project_number UNIQUE USING INDEX ...`.
- `idx_episodes_project_number`: `postgresql_concurrently=True` in autocommit block.
- `DROP INDEX IF EXISTS` guards before each concurrent create (rerun-safe after a failed
  CONCURRENTLY build, which leaves an INVALID index).

### 3. 004 / 005 / 008 / 012 — CONCURRENTLY for indexes on pre-existing tables
Wrap each `op.create_index` in `op.get_context().autocommit_block()` with
`postgresql_concurrently=True` + drop-if-exists guard. 008 keeps the column adds
transactional; 012 keeps guard/collision-check/UPDATE transactional, index moves after.

### 4. 011 — deliberately NOT concurrent (documented deviation)
`analytics_events` is created in the same migration: the table is empty and invisible to
other transactions, so plain CREATE INDEX blocks nothing; CONCURRENTLY would only add
partial-failure modes. Add a comment saying so.

### 5. env.py — import the whole model package
Replace the hand-maintained 11-model import with `import src.models` (package `__init__`
registers all models on Base.metadata). Comment warns against regressing to a hand-list.

### 6. New test — metadata == migrated schema
`tests/test_migration_metadata.py`: table-name set of `Base.metadata` (after importing
`src.models`) == tables in the live migrated test DB (minus `alembic_version`).
Catches both drift directions. (Column-level autogenerate-clean check is NOT possible yet —
known model/migration drift, see memory: billing FKs in 010 absent from models.)

### 7. Update existing unit tests (TDD: first)
- 004/005/012: assert `postgresql_concurrently=True` and autocommit_block usage.
- 006: rewrite — dupe-renumber SQL precedes backfill; NOT VALID→VALIDATE→SET NOT NULL
  ordering; concurrent unique index + USING INDEX attach; row_security guard still first.

## Verification
- `uv run pytest tests/` (full suite, CI parity)
- Demo (Phase 11): fresh scratch DB → migrate to 005 → seed dupes + NULLs → run 006 →
  show renumbering, constraint present, no abort. Plus `alembic upgrade head` on fresh DB.
- ruff + pre-commit.

## Non-goals
- Downgrade paths stay plain (dev-only).
- No column-level autogenerate assertion (blocked by known model drift #308).
- No changes to 013–017.
