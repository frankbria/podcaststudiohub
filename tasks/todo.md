# Issue #502 — Snippet deletion orphans S3 objects (bypasses StorageDeletionOutbox)

Plan source: issue body ("Fix" section). No architectural fork — the design is prescribed
(mirror `episode_service.delete_episode`, #366). Approved autonomously.

## Steps
1. Worktree `../worktrees/issue-502-snippet-delete-outbox`, branch `feature/issue-502-snippet-delete-outbox`.
2. RED: tests in `apps/api/tests/test_audio_snippets.py`
   - delete with s3_key → one outbox row (tenant_id = snippet tenant, file_path NULL), no synchronous `StorageService.delete_file`
   - delete without s3_key → no outbox row for that tenant
   - drain trigger called post-commit; broker failure only logs
3. GREEN: `delete_audio_snippet` enqueues `StorageDeletionOutbox(tenant_id, s3_key)` before `db.delete`,
   drops the try/except + direct `delete_file`, triggers `drain_storage_deletion_outbox.delay()` after commit
   (same broker-failure guard as episode_service).
4. Docstring update; deslop; quality gate (pytest+cov, diff-cover, ruff, opencode review, mutation check).
5. PR → post-PR review comment → demo (Showboat, API-only) → docs sync → CI → merge → disposition.

## Autonomous decisions
- `snippet.file_path` is NOT enqueued: upload unlinks the temp file in `finally`, and `file_path` is set
  to the S3 key (or a pseudo path) — there is never a local file to reclaim. Only `s3_key` is queued.
- Outbox drain is triggered eagerly after commit (as episode does) so tenant-visible deletion is prompt
  when the broker is up; beat covers the rest.

## Acceptance (PR #536 merged 79b0bf3; review fix: no phantom s3_key when S3 unconfigured; follow-up #537)
- [x] Snippet deletion enqueues an outbox row inside the same transaction as the row delete
- [x] The direct `delete_file` call and its blind catch are gone
- [x] A test asserts an outbox row is created (mirroring `test_delete_episode_with_s3_key_queues_outbox_row`)
- [x] GC drain picks up snippet keys — tenant_id/s3_key columns match what the drain expects
