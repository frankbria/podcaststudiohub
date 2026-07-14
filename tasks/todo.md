# Issue #319 — [P5.3] DR/durability hardening (self-authored plan)

Plan source: self-authored (no plan comment on issue; only a CodeRabbit stub).

## Already in the repo (verified, no work needed)
- Nightly off-host `pg_dump` → S3 + retention: `deployment/scripts/backup-db.sh` + systemd timer (#293)
- Tested Postgres restore runbook w/ RTO/RPO in `deployment/README.md` (RPO ≤ 24h, RTO ≈ minutes)
- S3 versioning script `deployment/scripts/enable-s3-versioning.sh` + README "required" step
- Stuck-job reaper `reap_stuck_episodes` (beat, every 300s, 45m threshold) — the "or add a stuck-job reaper" half of AC2 already exists

## Open gaps → steps (TDD: step 1 first, RED)

1. **Tests (RED)** — new `deployment/tests/test_dr_durability.py` (pattern: `test_db_backup.py`, static asserts):
   - deploy-dev.yml server-side block runs `backup-db.sh` BEFORE `alembic upgrade head` (positional assert)
   - workflow rsyncs `backup-db.sh` to the server
   - `configure-redis-persistence.sh` exists, executable, `set -euo pipefail`, sets `appendonly yes` + `CONFIG REWRITE`
   - README documents: Redis durability stance (AOF + reaper backstop + what a flush loses), S3 MFA-delete, S3 object restore runbook (`list-object-versions` / delete-marker removal)

2. **Pre-migration dump gate** — `.github/workflows/deploy-dev.yml` Deploy API step:
   - rsync `deployment/scripts/backup-db.sh` → `$SERVER_PATH/deployment/scripts/`
   - in the `set -e` SSH block, before `uv run alembic upgrade head`: source `$SERVER_PATH/api/.env`, run `backup-db.sh` with `DB_BACKUP_S3_PREFIX=db-backups/pre-migration/` (script hard-fails w/o bucket/creds or on empty dump → deploy aborts before migration; prefix is self-pruned by the script's own retention)
   - mirror the dump step in README manual-deploy Step 2

3. **Redis durability (decision: enable AOF, keep reaper as backstop)** — new `deployment/scripts/configure-redis-persistence.sh`: idempotent, `CONFIG SET appendonly yes` + `appendfsync everysec` + `CONFIG REWRITE` + verify readback. README section: stance, what a flush loses (queued/in-flight jobs; ephemeral-by-design: rate-limit counters, OAuth state, idempotency locks), reaper marks stranded episodes failed after 45m (no auto-requeue; user retries).

4. **S3 DR docs** — README: MFA-delete as optional hardening (root-MFA-only op, can't be scripted with app creds); S3 object restore runbook (recover deleted/overwritten object from versions) + S3 RTO/RPO statement.

5. **Gates** — `python -m pytest deployment/tests/`, ruff, demo evidence per AC, PR, reviews, merge.

## Acceptance criteria checklist
- [ ] Off-host pg_dump before migrate, gating the deploy (step 2)
- [ ] Redis durability decided + documented: AOF enabled via script + reaper documented as backstop (step 3)
- [ ] S3 versioning enabled (script + README already exist; MFA-delete documented — step 4)
- [ ] Postgres+S3 restore runbook with RTO/RPO, tested (Postgres exists; add S3 — step 4; tests — step 1)

## Autonomous decisions (no fork)
- Reuse `backup-db.sh` for the pre-migration dump instead of a new script (same contract, self-pruning prefix).
- AOF `everysec` (≤1s broker loss) over RDB-only; reaper stays as the stranded-episode backstop.
- `.env` is sourced in the deploy shell — values must stay shell-sourceable (they are today; noted in README).
- MFA-delete documented, not scripted (requires root-account MFA; app IAM user cannot toggle it).
