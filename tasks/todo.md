# Issue #312 — Distribution idempotency (P3.9)

**Problem**: `distribute_to_platform_task` (max_retries=5, acks_late) has no idempotency guard —
a redelivery after a successful publish re-publishes to Spotify/Apple or re-POSTs the webhook.

**Plan source**: CodeRabbit comment (verified against current code 2026-07-10; matches exactly).
**Design choice**: record success in-task via existing `generation_progress["distribution"]` +
`SELECT FOR UPDATE` pattern (no new table). Callback stays as idempotent redundancy.

## Steps

- [x] 1. Tests first (RED): 17 unit tests (`test_distribution_idempotency.py`)
- [x] 2. Services: optional `idempotency_key` → `Idempotency-Key` header
- [x] 3. `platform_distribution.py`: `_idempotency_key()` helper (derived in helpers, not threaded — shorter diff), webhook header+payload, locked pre-check skip, in-task `record_platform_distribution` (extracted from `on_distribution_complete`)
- [x] 4. Full suite 1720 passed, coverage 94.05%; ruff clean
- [x] 5. Reviews (opencode pre-PR + post-PR, triaged), PR #371, demo posted
- [x] 6. **Demo-found bug**: migration 001 `episodes_status_check` rejected `distributing`/`composing`/`uploading`/`distribution_failed` → callbacks silently never recorded results. Fixed via migration 016 + constraint regression test + web status labels. Filed #372 (psycopg Jsonb test-isolation poisoning).
- [x] 7. CI green (12 checks) → squash-merged as PR #371 (2026-07-10)

## Acceptance criteria (from issue)
- Pre-publish check skips platforms already recorded complete (locked read)
- Stable `{episode_id}:{platform}` idempotency key passed to platform API + webhook payload/header
- Success recorded transactionally
