# Issue #318 — Migration safety: dedupe-safe 006, lock-safe DDL, complete env.py metadata

*2026-07-14T20:40:47Z*

Acceptance criteria from #318: (1) detect/renumber duplicate (project_id, episode_number) rows before adding the unique constraint; (2) build large-table indexes CONCURRENTLY in autocommit blocks and use NOT VALID → VALIDATE for NOT NULL; (3) import all current models into alembic target_metadata and assert metadata == model set in a test. This demo exercises each criterion against real PostgreSQL scratch databases. First: create a fresh DB and migrate to revision 005 (just before the hardened 006).

```bash
docker exec api-postgres-1 psql -U lull -d podcastfy -q -c "DROP DATABASE IF EXISTS mig318_demo;" -c "CREATE DATABASE mig318_demo OWNER podcastfy;"
PW=$(grep "^DATABASE_URL=" .env | sed -E "s|.*//podcastfy:([^@]*)@.*|\1|")
DATABASE_URL="postgresql+asyncpg://podcastfy:${PW}@localhost:5432/mig318_demo" uv run alembic upgrade 005 2>&1 | tail -2
```

```output
NOTICE:  database "mig318_demo" does not exist, skipping
INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, Add missing indexes for discriminator and status columns
INFO  [alembic.runtime.migration] Running upgrade 004 -> 005, Add missing index on episode_compositions.layout_id foreign key
```

**Criterion 1 — duplicates are renumbered, not fatal.** Seed the exact data shape that aborted the old 006: project A has a triplicate episode_number (2,2,2) plus numbers 1 and 7 and two NULLs; project B has a duplicate pair (1,1) plus a NULL.

```bash
docker exec -i api-postgres-1 psql -U podcastfy -d mig318_demo -v ON_ERROR_STOP=1 -q <<SQL
INSERT INTO users (id, tenant_id, email, password_hash) VALUES
 ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000aa','demo@example.com','x');
INSERT INTO projects (id, tenant_id, user_id, name)
SELECT gen, '00000000-0000-0000-0000-0000000000aa', '00000000-0000-0000-0000-000000000001', n FROM (VALUES
 ('00000000-0000-0000-0000-000000000010'::uuid,'Project A'),
 ('00000000-0000-0000-0000-000000000020'::uuid,'Project B')) v(gen,n);
INSERT INTO episodes (id, tenant_id, user_id, project_id, episode_number, created_at)
SELECT gen_random_uuid(), '00000000-0000-0000-0000-0000000000aa', '00000000-0000-0000-0000-000000000001',
       '00000000-0000-0000-0000-000000000010', n, ts::timestamptz
FROM (VALUES (1,'2026-01-01'),(2,'2026-01-02'),(2,'2026-01-03'),(2,'2026-01-04'),(7,'2026-01-05'),(NULL,'2026-01-06'),(NULL,'2026-01-07')) v(n,ts);
INSERT INTO episodes (id, tenant_id, user_id, project_id, episode_number, created_at)
SELECT gen_random_uuid(), '00000000-0000-0000-0000-0000000000aa', '00000000-0000-0000-0000-000000000001',
       '00000000-0000-0000-0000-000000000020', n, ts::timestamptz
FROM (VALUES (1,'2026-02-01'),(1,'2026-02-02'),(NULL,'2026-02-03')) v(n,ts);
SQL
docker exec api-postgres-1 psql -U podcastfy -d mig318_demo -c "SELECT left(project_id::text,13) AS project, episode_number, created_at::date FROM episodes ORDER BY project_id, created_at;"
```

```output
    project    | episode_number | created_at
---------------+----------------+------------
 00000000-0000 |              1 | 2026-01-01
 00000000-0000 |              2 | 2026-01-02
 00000000-0000 |              2 | 2026-01-03
 00000000-0000 |              2 | 2026-01-04
 00000000-0000 |              7 | 2026-01-05
 00000000-0000 |                | 2026-01-06
 00000000-0000 |                | 2026-01-07
 00000000-0000 |              1 | 2026-02-01
 00000000-0000 |              1 | 2026-02-02
 00000000-0000 |                | 2026-02-03
(10 rows)

```

Now run `alembic upgrade head` over this dirty data. The old 006 aborted here with a unique-constraint violation; the hardened 006 renumbers duplicates first (earliest created_at keeps its number, later rows move above the project max), then backfills NULLs, then applies NOT NULL via CHECK NOT VALID → VALIDATE → SET NOT NULL and builds the unique index CONCURRENTLY (criterion 2).

```bash
PW=$(grep "^DATABASE_URL=" .env | sed -E "s|.*//podcastfy:([^@]*)@.*|\1|")
DATABASE_URL="postgresql+asyncpg://podcastfy:${PW}@localhost:5432/mig318_demo" uv run alembic upgrade head 2>&1 | grep -E "005 -> 006|016 -> 017"
```

```output
INFO  [alembic.runtime.migration] Running upgrade 005 -> 006, Make episode_number NOT NULL with auto-increment per project
INFO  [alembic.runtime.migration] Running upgrade 016 -> 017, Add storage_deletion_outbox table for durable storage erasure (issue #366)
```

The full chain reached 017 with no abort. Outcome: project A (…10) kept 1, 2 (earliest of the triplicate), 7; the two later duplicates were renumbered to 8 and 9 (above the old max 7); NULLs backfilled to 10, 11. Project B (…20) kept the earlier 1, renumbered the other to 2, backfilled the NULL to 3.

```bash
docker exec api-postgres-1 psql -U podcastfy -d mig318_demo -c "SELECT right(project_id::text,2) AS proj, episode_number, created_at::date FROM episodes ORDER BY project_id, episode_number;"
```

```output
 proj | episode_number | created_at
------+----------------+------------
 10   |              1 | 2026-01-01
 10   |              2 | 2026-01-02
 10   |              7 | 2026-01-05
 10   |              8 | 2026-01-03
 10   |              9 | 2026-01-04
 10   |             10 | 2026-01-06
 10   |             11 | 2026-01-07
 20   |              1 | 2026-02-01
 20   |              2 | 2026-02-02
 20   |              3 | 2026-02-03
(10 rows)

```

Verify the constraints landed: the unique constraint exists (contype u), episode_number is NOT NULL, and both indexes are present. The transient NOT-VALID check constraint was cleaned up.

```bash
docker exec api-postgres-1 psql -U podcastfy -d mig318_demo -c "SELECT conname, contype FROM pg_constraint WHERE conrelid = 'episodes'::regclass AND conname LIKE '%episode_number%' OR conname = 'uq_episodes_project_number';" -c "SELECT attname, attnotnull FROM pg_attribute WHERE attrelid = 'episodes'::regclass AND attname = 'episode_number';" -c "SELECT indexname FROM pg_indexes WHERE tablename = 'episodes' AND indexname LIKE '%project_number%';"
```

```output
          conname           | contype
----------------------------+---------
 uq_episodes_project_number | u
(1 row)

    attname     | attnotnull
----------------+------------
 episode_number | t
(1 row)

          indexname
-----------------------------
 uq_episodes_project_number
 idx_episodes_project_number
(2 rows)

```

**Criterion 2 — CONCURRENTLY in the migration source.** The index builds in 004/005/006/008/012 use postgresql_concurrently inside autocommit blocks, and 006 uses the NOT VALID → VALIDATE sequence. (011 is deliberately non-concurrent: analytics_events is created in that same migration, so it is empty and invisible to other transactions.)

```bash
grep -c "postgresql_concurrently=True\|CONCURRENTLY" alembic/versions/004_add_missing_discriminator_indexes.py alembic/versions/005_add_fk_indexes.py alembic/versions/006_make_episode_number_not_null.py alembic/versions/008_add_celery_task_tracking.py alembic/versions/012_canonicalize_user_emails.py
grep -n "NOT VALID\|VALIDATE CONSTRAINT\|SET NOT NULL" alembic/versions/006_make_episode_number_not_null.py | head -5
```

```output
alembic/versions/004_add_missing_discriminator_indexes.py:4
alembic/versions/005_add_fk_indexes.py:3
alembic/versions/006_make_episode_number_not_null.py:6
alembic/versions/008_add_celery_task_tracking.py:3
alembic/versions/012_canonicalize_user_emails.py:3
9:Lock-safety (issue #318): NOT NULL is applied via CHECK ... NOT VALID ->
10:VALIDATE -> SET NOT NULL (PostgreSQL 12+ uses the validated check to skip the
117:	# EXCLUSIVE. The NOT VALID add is a brief lock; the scan happens in
118:	# VALIDATE (SHARE UPDATE EXCLUSIVE — writes continue); SET NOT NULL then
129:		"CHECK (episode_number IS NOT NULL) NOT VALID"
```

**Criterion 3 — env.py metadata completeness.** env.py now imports the whole src.models package (no hand-maintained list), and a new test asserts the Base.metadata table set equals the migrated schema — it fails in both drift directions. Run it against the migrated dev DB, plus the full migration unit-test set.

```bash
grep -n "import src.models" alembic/env.py
uv run pytest tests/test_migration_metadata.py tests/unit/test_migration_004_discriminator_indexes.py tests/unit/test_migration_005_fk_indexes.py tests/unit/test_migration_006_episode_number_not_null.py tests/unit/test_migration_012_canonicalize_user_emails.py -q --no-cov 2>&1 | tail -1
```

```output
18:import src.models  # noqa: F401
============================== 48 passed in 0.23s ==============================
```

Finally, CI parity: a pure fresh single-shot upgrade to head (what CI runs on every PR) still works with the CONCURRENTLY/autocommit changes, and scratch databases are cleaned up.

```bash
docker exec api-postgres-1 psql -U lull -d podcastfy -q -c "DROP DATABASE IF EXISTS mig318_fresh;" -c "CREATE DATABASE mig318_fresh OWNER podcastfy;" 2>/dev/null
PW=$(grep "^DATABASE_URL=" .env | sed -E "s|.*//podcastfy:([^@]*)@.*|\1|")
DATABASE_URL="postgresql+asyncpg://podcastfy:${PW}@localhost:5432/mig318_fresh" uv run alembic upgrade head 2>&1 | tail -1
docker exec api-postgres-1 psql -U lull -d podcastfy -q -c "DROP DATABASE mig318_demo;" -c "DROP DATABASE mig318_fresh;" && echo "scratch DBs dropped"
```

```output
INFO  [alembic.runtime.migration] Running upgrade 016 -> 017, Add storage_deletion_outbox table for durable storage erasure (issue #366)
scratch DBs dropped
```

All three acceptance criteria demonstrated with outcome evidence. The full backend suite (1824 passed, 7 skipped, coverage gates enforced) ran green on this branch before the PR was opened: see PR #398.
