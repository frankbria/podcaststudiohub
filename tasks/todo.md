# Issue #301 [P2.3] — Migration backfills (006/012) silently no-op under FORCE RLS

**Branch:** `fix/301-migration-rls-backfill`
**Strategy (issue-chosen option 3):** dedicated privileged migration URL + fail-loud guard + tests.

## Root cause
003 applies FORCE ROW LEVEL SECURITY to tenant tables keyed on the unset `app.tenant_id`
GUC. When 006/012 backfills run under a role subject to RLS (the documented `podcastfy_app`,
or a plain owner under FORCE), UPDATEs match zero rows and silently no-op — then NOT NULL /
unique-index constraints build over un-backfilled data. Outcome depends entirely on which
role runs migrations.

## Tasks
1. **config**: add `MIGRATION_DATABASE_URL: Optional[str] = None` to `Settings` (apps/api/src/config.py).
2. **alembic env**: source URL from `MIGRATION_DATABASE_URL or DATABASE_URL` (apps/api/alembic/env.py).
3. **harden 006**: `SET LOCAL row_security = off` before the backfill (006_make_episode_number_not_null.py).
4. **harden 012**: `SET LOCAL row_security = off` before collision SELECT + UPDATE (012_canonicalize_user_emails.py).
5. **unit tests (RED→GREEN)**: extend test_migration_006 to assert SET LOCAL emitted before backfill;
   add test_migration_012 asserting same + preserved collision/RuntimeError + index order.
6. **CI**: reframe `migrate-as-non-superuser` job to the two-role model:
   - positive: migration role NOSUPERUSER NOCREATEDB NOCREATEROLE **BYPASSRLS** + `MIGRATION_DATABASE_URL` → `alembic upgrade head` succeeds.
   - negative: a non-BYPASSRLS owner role on a fresh DB → `alembic upgrade head` must FAIL at 006/012
     (satisfies "test running migrations as the non-privileged role").
7. **docs**: MIGRATION_DATABASE_URL in apps/api/.env.example, root .env.example, docs/env_inventory.md, deployment/README.md.

## Acceptance criteria (from issue)
- [ ] Dedicated MIGRATION_DATABASE_URL documented + wired.
- [ ] Backfills fail loudly (not silently) under an RLS-subject role.
- [ ] Test runs migrations as the non-privileged role and proves fail-loud.
