# Issue #366 — Durable storage-erasure queue (outbox/GC) for delete flows (P3.10)

**Problem** (follow-up to #308): S3/local cleanup in `delete_episode` and `erase_user` is
best-effort and runs **before** the DB commit. Two windows: (1) commit fails after storage
deletion → rows point at deleted audio; (2) in-flight generation TOCTOU → a task finishing
after the 409 check / episode delete uploads audio that is orphaned forever (IAM has no
`s3:ListBucket`, so orphans are unfindable).

**Plan source**: self-authored (issue prescribes the architecture: durable deletion outbox +
periodic GC worker; no plan comment existed).

## Design (autonomous decisions)

- **Pure outbox**: delete flows stop touching storage entirely. They insert
  `storage_deletion_outbox` rows (s3_key / file_path) **in the same transaction** as the row
  deletes, then commit. Commit fails → nothing was deleted from storage (closes window 1).
- **Prompt drain**: post-commit, best-effort `drain_storage_deletion_outbox.delay()` so audio
  disappears promptly; the beat schedule is the durable backstop.
- **GC task** in existing `src/tasks/maintenance.py` (same module as the reaper): batch
  `SELECT … FOR UPDATE SKIP LOCKED`, delete via `StorageService.delete_file` / `os.remove`
  (missing local file = success; S3 delete_object is idempotent), delete row on success,
  `attempts += 1` + `last_attempt_at` on failure. Loops while a full batch was processed.
- **Absorb late uploads** (closes window 2): where upload results are persisted and the episode
  row is found missing (`finalize_episode_generation_task`, `callbacks.on_upload_complete`, and
  composition persist if applicable), insert an outbox row for the just-uploaded key instead of
  only logging.
- **No RLS on the outbox table** (deliberate): internal, never API-exposed; the Celery worker
  must drain cross-tenant. `tenant_id` kept as a plain nullable UUID for audit. GRANT to
  `podcastfy_app` in the migration.
- **Beat actually runs**: `beat_schedule` exists but no deployment starts a beat process (the
  reaper never fires in prod!). Add `-B` (embedded beat) to the single celery worker command in
  deploy configs.
- Keep: erase_user 409 guard (defense in depth); episode delete stays guard-free (it's the only
  abort mechanism — per issue comment); absorb covers its orphan window.

## Steps

- [x] 1. Migration `017_add_storage_deletion_outbox` (+ structure unit test): table
  (id UUID PK, tenant_id UUID null, s3_key Text null, file_path Text null,
  CHECK s3_key/file_path not both null, attempts int default 0, created_at, last_attempt_at),
  ix on created_at, GRANT, downgrade. Model `src/models/storage_deletion_outbox.py`,
  registered in `models/__init__.py`.
- [x] 2. `delete_episode` (episode_service.py:313-365): replace inline `storage.delete_file` /
  `os.remove` loops with outbox inserts in-session; delete + commit; post-commit best-effort
  `.delay()`. Update existing tests asserting inline deletion.
- [x] 3. `erase_user` (offboarding_service.py): same rewire — existing key collection stays,
  inserts replace inline deletion, cascade delete + audit + commit, post-commit `.delay()`.
  Return shape becomes "queued" counts (endpoint returns 204; contract-safe).
- [x] 4. `drain_storage_deletion_outbox` task in maintenance.py + `task_routes` entry +
  `beat_schedule` entry (interval setting in config.py, mirror reaper's). Tests mirror
  `test_maintenance.py` (mock SyncSessionLocal + StorageService).
- [x] 5. Absorb late uploads in `finalize_episode_generation_task` + `on_upload_complete`
  (+ composition callback if it persists keys): missing episode row → outbox insert via sync
  session. Tests: upload completes after delete → key lands in outbox. Composition callback
  confirmed N/A — `merge_audio_snippets_task` never uploads to S3 and `composed_s3_key` is
  never written anywhere in the codebase (only declared and read by the delete flows), so
  there's no composition-path orphan window to absorb.
- [x] 6. Deployment: add `-B` to celery worker command in `.github/workflows/deploy-dev.yml`,
  `deployment/README.md`, `scripts/repo-maintainer/setup-demo-vps.sh` (single-worker
  assumption noted).
- [x] 7. Quality gate done: 1751 passed / 7 pre-existing skips; diff coverage 100% (0 missing
  lines); ruff clean; mutation check 4/4 killed; deslop clean (1 observation fixed: tenant_id
  threaded into finalize absorb). Reviews: internal Critical fixed (content-source s3_keys
  orphaned on episode delete); codex cross-family P2 fixed (absorb outbox insert now retried
  inline + CRITICAL last-resort log); my own review fixed GC zero-progress hot loop + locked
  the delete-flow key reads (TOCTOU). opencode timed out twice → codex served as the
  cross-family reviewer.
- [ ] 8. PR → post-PR review comment → demo (hard gate) → CI green → docs sync → merge.

## Acceptance criteria

- [x] AC1: DB commit failure during a delete flow leaves storage untouched (no deletion before commit).
- [x] AC2: Intended deletions are durably recorded and retried until success (attempts tracked).
- [x] AC3: Late Celery upload after episode/account deletion gets absorbed into the outbox (no permanent orphan).
- [x] AC4: GC runs periodically in deployed env (beat process actually scheduled) and promptly post-delete.
- [x] AC5: Only `delete_object` on known keys — no `s3:ListBucket` dependency.
- [x] AC6: erase_user 409 guard unchanged; episode delete remains guard-free.
