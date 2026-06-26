# Issue #293 — [P0.3] No automated PostgreSQL backup/restore

**Approach (lazy-correct):** nightly logical `pg_dump` off-host to S3 with retention via a
systemd timer, plus a tested restore script + runbook. Not pgBackRest/WAL-G — the AC allows
"or", and continuous archiving is overkill for a single dev VPS. RPO ≤ 24h, RTO ~minutes.

Conventions matched: idempotent bash in `deployment/scripts/` (`set -euo pipefail`, header
block w/ issue ref, like `harden-host.sh`/`enable-s3-versioning.sh`); static contract tests in
`deployment/tests/` that read the scripts (no execution); README ops section.

## Steps
1. **`deployment/scripts/backup-db.sh`** — `pg_dump -Fc` (custom format) | gzip → timestamped
   S3 key under a configurable bucket/prefix (`DB_BACKUP_S3_BUCKET` default = `AWS_S3_BUCKET`,
   `DB_BACKUP_S3_PREFIX` default `db-backups/`). Reads `DATABASE_URL` (or `PG*`). Prunes remote
   objects older than `DB_BACKUP_RETENTION_DAYS` (default 14). `set -euo pipefail`, idempotent.
2. **`deployment/scripts/install-db-backup-timer.sh`** — installs a systemd service + nightly
   timer running `backup-db.sh` as the `podcastfy` service account. Idempotent (run once as root).
3. **`deployment/scripts/restore-db.sh`** — download a chosen (or latest) backup from S3 and
   `pg_restore` into a target DB. Confirmation guard before clobbering. This is the tested path.
4. **README "Database Backup & Restore (DR)" section** — install steps, retention, restore
   runbook with RTO/RPO targets, IAM note (backup user needs `s3:PutObject`/`GetObject`/
   `ListBucket`/`DeleteObject` on the backup prefix), and a restore-test procedure.
5. **`deployment/tests/test_db_backup.py`** — static contract tests (scripts exist+executable,
   pg_dump→S3+prune present, timer targets service account, restore guards + pg_restore, README
   documents runbook + RTO/RPO).

## Acceptance criteria
- [ ] Automated off-host nightly logical dump to object storage with retention, via systemd timer
- [ ] Documented and tested restore runbook with target RTO/RPO

---

# Production-Readiness Plan — Podcastfy Studio Hub SaaS Launch

**Verdict: NOT READY.** 10 blockers across data durability, core flows, billing, and a crashing UI feature.
Source: 252-agent fan-out audit (18 reviewer areas, ~130 raw findings → 35 deduplicated, verified issues).

Work `[P0.1] → … → [P6.2]` in order; no issue depends on a later one. Each issue is atomic (one developer, one session).

| PX.Y | Sev | Issue |
|------|-----|-------|
| P0.1 | critical | StorageService reads non-existent setting S3_BUCKET_NAME — episode download and RSS upload are broken |
| P0.2 | critical | Generated audio is lost and undownloadable when AWS_S3_BUCKET is unset |
| P0.3 | critical | No automated PostgreSQL backup/restore — single VPS disk is the only copy of all tenant data |
| P0.4 | high | Generation failures and time-limit kills leave episodes stuck at 'queued' forever |
| P0.5 | high | acks_late + reject_on_worker_lost re-runs the full paid LLM/TTS pipeline (no idempotency guard) |
| P1.1 | high | billing_usage has no unique constraint on (user_id, period_start) — duplicate rows and 500s |
| P1.2 | high | Usage metering and plan-limit enforcement are dead code (never invoked) |
| P1.3 | medium | Mock Stripe checkout URL ships in production when Stripe is unconfigured |
| P2.1 | high | TTS Settings dialog crashes via empty-string Radix SelectItem once a config is saved |
| P2.2 | high | on_distribution_complete silently drops failed distributions; episode marked 'complete' with no trace |
| P2.3 | high | Migration backfills (006/012) silently no-op under FORCE RLS when run as the documented non-superuser role |
| P2.4 | high | E2E suite is disabled (9/10 specs fixme'd) with broken helpers — CI reports false green for core flows |
| P2.5 | medium | Coverage gates are hollow: backend --cov-fail-under=0 and frontend excludes all of src/app/** |
| P3.1 | medium | RLS defense-in-depth gaps: hardcoded DB password, USING(true) users SELECT, WITH CHECK(true) inserts, and new tables with no RLS |
| P3.2 | medium | Webhook test-connection performs an unpinned, unrevalidated server-side fetch (SSRF / DNS-rebinding TOCTOU) |
| P3.3 | medium | Dependabot only scans github-actions — no pip/npm CVE alerting; auth-crypto libs are unmaintained |
| P3.4 | medium | CSP weakened by 'unsafe-inline' script-src; production build ignores TS/ESLint errors |
| P3.5 | medium | Episode delete orphans S3 audio forever; no tenant-offboarding / GDPR erasure path |
| P3.6 | medium | Wrong transcript_path persisted for every episode; engine audio/transcript artifacts never cleaned up |
| P3.7 | medium | datetime.utcnow() in analytics/RSS/usage creates naive datetimes — analytics query raises on TZ-aware params |
| P3.8 | medium | finalize_episode_generation_task cleanup fails when the DB session is already in a failed-transaction state |
| P3.9 | medium | Platform distribution retries can republish episodes (no idempotency key) |
| P4.1 | medium | Audio-composition workflow is unwired — enabling the flag composes empty audio and drops the real podcast |
| P4.2 | medium | Multi-modal input (YouTube/PDF/image/topic) is advertised but not implemented end-to-end |
| P4.3 | medium | Spotify/Apple direct-publish targets POST to endpoints that are not real publishing APIs |
| P4.4 | medium | Distribution, RSS feed, and analytics have backend support but no frontend surface |
| P5.1 | medium | nginx upstream ports drift: provision-ssl.sh installs 8001/3003 while deploy/docs use 8005/3010 (502s) |
| P5.2 | medium | Migration safety: 006 unique constraint aborts on pre-existing duplicates; non-CONCURRENT DDL locks; env.py metadata incomplete |
| P5.3 | medium | DR/durability hardening: migration runs mid-deploy with no pre-migration dump; Redis durability undocumented; S3 not version-protected |
| P5.4 | medium | Observability gaps: no error tracking, /health doesn't check DB/Redis, no readiness probe, no correlation IDs, no log rotation |
| P5.5 | medium | Blocking synchronous boto3 calls inside async handlers and StorageService pin the event loop |
| P5.6 | medium | Backend performance: N+1 team counts, inline external URL HEAD blocking creates, per-event analytics commits, unindexed episode search |
| P5.7 | medium | Frontend accessibility defects: nested <main>/broken skip link, light-only toasts, unannounced auth errors, role=button nesting |
| P6.1 | low | Docs drift and repo hygiene: contradictory README, mislabeled 36MB tracked data, broken Sphinx tooling, stale agent reports, committed scaffolding |
| P6.2 | low | Geographic analytics (top_countries) is wired but always returns empty — country is never populated |

## Phases


### P0 — Launch blockers — data loss & broken core flow

- **[P0.1]** (critical) StorageService reads non-existent setting S3_BUCKET_NAME — episode download and RSS upload are broken
  ↳ Prerequisite for P0.2; unblocks episode download + RSS upload.
- **[P0.2]** (critical) Generated audio is lost and undownloadable when AWS_S3_BUCKET is unset
  ↳ Depends on P0.1 (storage bucket resolution).
- **[P0.3]** (critical) No automated PostgreSQL backup/restore — single VPS disk is the only copy of all tenant data
  ↳ Independent. Highest data-durability priority.
- **[P0.4]** (high) Generation failures and time-limit kills leave episodes stuck at 'queued' forever
  ↳ Core generation flow. Prerequisite for P0.5 and P2.2.
- **[P0.5]** (high) acks_late + reject_on_worker_lost re-runs the full paid LLM/TTS pipeline (no idempotency guard)
  ↳ Depends on P0.4 (terminal status handling).

### P1 — Billing correctness & abuse prevention

- **[P1.1]** (high) billing_usage has no unique constraint on (user_id, period_start) — duplicate rows and 500s
  ↳ Prerequisite for P1.2 (metering writes need the unique constraint).
- **[P1.2]** (high) Usage metering and plan-limit enforcement are dead code (never invoked)
  ↳ Depends on P1.1 (constraint) and P0.5 (no double-metering on re-run).
- **[P1.3]** (medium) Mock Stripe checkout URL ships in production when Stripe is unconfigured
  ↳ Gate before charging real customers.

### P2 — Core correctness, reliability & test-trust

- **[P2.1]** (high) TTS Settings dialog crashes via empty-string Radix SelectItem once a config is saved
  ↳ Independent UI blocker.
- **[P2.2]** (high) on_distribution_complete silently drops failed distributions; episode marked 'complete' with no trace
  ↳ Relates to P0.4 (terminal status correctness).
- **[P2.3]** (high) Migration backfills (006/012) silently no-op under FORCE RLS when run as the documented non-superuser role
  ↳ Migration data-correctness under RLS.
- **[P2.4]** (high) E2E suite is disabled (9/10 specs fixme'd) with broken helpers — CI reports false green for core flows
  ↳ Test-trust: restore real signal before relying on CI.
- **[P2.5]** (medium) Coverage gates are hollow: backend --cov-fail-under=0 and frontend excludes all of src/app/**
  ↳ Depends on P2.4 (meaningful suite first).

### P3 — Security & data-integrity hardening

- **[P3.1]** (medium) RLS defense-in-depth gaps: hardcoded DB password, USING(true) users SELECT, WITH CHECK(true) inserts, and new tables with no RLS
  ↳ Defense-in-depth + secret hygiene.
- **[P3.2]** (medium) Webhook test-connection performs an unpinned, unrevalidated server-side fetch (SSRF / DNS-rebinding TOCTOU)
  ↳ SSRF on webhook test-connection.
- **[P3.3]** (medium) Dependabot only scans github-actions — no pip/npm CVE alerting; auth-crypto libs are unmaintained
  ↳ CVE alerting for pip/npm.
- **[P3.4]** (medium) CSP weakened by 'unsafe-inline' script-src; production build ignores TS/ESLint errors
  ↳ CSP + prod build error gating.
- **[P3.5]** (medium) Episode delete orphans S3 audio forever; no tenant-offboarding / GDPR erasure path
  ↳ Tenant offboarding / GDPR erasure.
- **[P3.6]** (medium) Wrong transcript_path persisted for every episode; engine audio/transcript artifacts never cleaned up
  ↳ Artifact correctness + cleanup.
- **[P3.7]** (medium) datetime.utcnow() in analytics/RSS/usage creates naive datetimes — analytics query raises on TZ-aware params
  ↳ Naive-datetime correctness.
- **[P3.8]** (medium) finalize_episode_generation_task cleanup fails when the DB session is already in a failed-transaction state
  ↳ Cleanup robustness on failed tx.
- **[P3.9]** (medium) Platform distribution retries can republish episodes (no idempotency key)
  ↳ Distribution idempotency.

### P4 — Feature-completeness gaps (advertised but unimplemented)

- **[P4.1]** (medium) Audio-composition workflow is unwired — enabling the flag composes empty audio and drops the real podcast
  ↳ Advertised feature, currently unwired.
- **[P4.2]** (medium) Multi-modal input (YouTube/PDF/image/topic) is advertised but not implemented end-to-end
  ↳ Multi-modal input completeness.
- **[P4.3]** (medium) Spotify/Apple direct-publish targets POST to endpoints that are not real publishing APIs
  ↳ Direct-publish targets are not real APIs.
- **[P4.4]** (medium) Distribution, RSS feed, and analytics have backend support but no frontend surface
  ↳ Frontend surface for existing backend.

### P5 — Infra, migrations, observability, performance & a11y

- **[P5.1]** (medium) nginx upstream ports drift: provision-ssl.sh installs 8001/3003 while deploy/docs use 8005/3010 (502s)
  ↳ nginx upstream port drift → 502s.
- **[P5.2]** (medium) Migration safety: 006 unique constraint aborts on pre-existing duplicates; non-CONCURRENT DDL locks; env.py metadata incomplete
  ↳ Migration safety hardening.
- **[P5.3]** (medium) DR/durability hardening: migration runs mid-deploy with no pre-migration dump; Redis durability undocumented; S3 not version-protected
  ↳ DR/durability hardening.
- **[P5.4]** (medium) Observability gaps: no error tracking, /health doesn't check DB/Redis, no readiness probe, no correlation IDs, no log rotation
  ↳ Observability/health/readiness.
- **[P5.5]** (medium) Blocking synchronous boto3 calls inside async handlers and StorageService pin the event loop
  ↳ Async event-loop blocking.
- **[P5.6]** (medium) Backend performance: N+1 team counts, inline external URL HEAD blocking creates, per-event analytics commits, unindexed episode search
  ↳ Backend performance.
- **[P5.7]** (medium) Frontend accessibility defects: nested <main>/broken skip link, light-only toasts, unannounced auth errors, role=button nesting
  ↳ Accessibility defects.

### P6 — Docs & low-priority polish

- **[P6.1]** (low) Docs drift and repo hygiene: contradictory README, mislabeled 36MB tracked data, broken Sphinx tooling, stale agent reports, committed scaffolding
  ↳ Docs/repo hygiene.
- **[P6.2]** (low) Geographic analytics (top_countries) is wired but always returns empty — country is never populated
  ↳ Geo analytics always empty.


---

# Issue #292 — [P0.2] Generated audio lost & undownloadable when AWS_S3_BUCKET is unset

**Approach (CodeRabbit Design Choice 1, option 2):** persistent local-disk fallback. The Episode
model already always persists file_path, so serve from disk when s3_key is absent instead of
forcing S3 on every deployment.

## Steps
1. **LOCAL_AUDIO_STORAGE_PATH setting** — config.py field next to AWS_* block, default project-relative
   storage/audio (persistent, not /tmp). Document in apps/api/.env.example + root .env.example.
2. **Persist audio out of /tmp** — finalize_episode_generation_task no-S3 branch: copy audio_file_path
   into LOCAL_AUDIO_STORAGE_PATH (mkdir), set episode.file_path before committing complete. S3 path unchanged.
3. **iter_local_file** in download_utils.py mirroring iter_s3_body (asyncio.to_thread, start/end range).
4. **Download endpoint local fallback** — episodes.py: keep complete guard; branch s3_key -> S3 path,
   elif file_path on disk -> serve locally (os.path.getsize, 200/206/416, identical headers), else 404.
5. **S3 versioning (operational)** — deployment/ helper script (aws s3api put-bucket-versioning
   Status=Enabled) + deployment/README.md S3 section step (admin action).
6. **Tests** — test_download_endpoint.py (200+206 local, fix missing_s3_key 404 needs both absent);
   test_s3_upload.py (file_path into LOCAL_AUDIO_STORAGE_PATH not /tmp); unit/test_download_utils.py
   (full + ranged iter_local_file).

## Acceptance criteria
- [ ] No-S3: episode complete AND downloadable (no /tmp loss)
- [ ] S3 bucket versioning enabled/documented
- [ ] Test for no-S3 path
- [ ] S3 path behavior unchanged
