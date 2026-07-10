# Issue #312 — Distribution idempotency (P3.9)

**Problem**: `distribute_to_platform_task` (max_retries=5, acks_late) has no idempotency guard —
a redelivery after a successful publish re-publishes to Spotify/Apple or re-POSTs the webhook.

**Plan source**: CodeRabbit comment (verified against current code 2026-07-10; matches exactly).
**Design choice**: record success in-task via existing `generation_progress["distribution"]` +
`SELECT FOR UPDATE` pattern (no new table). Callback stays as idempotent redundancy.

## Steps

- [ ] 1. Tests first (RED): unit tests in `apps/api/tests/unit/`
  - services: `publish_episode(idempotency_key=...)` sets `Idempotency-Key` header; absent → no header
  - webhook: key in header AND payload
  - task: platform already `complete` in generation_progress → short-circuit, no publish/POST, returns stored result
  - task: after successful publish, success merged into `generation_progress["distribution"][platform]` in-task (locked session)
- [ ] 2. `spotify_service.py` / `apple_podcasts_service.py`: optional `idempotency_key` param → `Idempotency-Key` header
- [ ] 3. `platform_distribution.py`:
  - derive `key = f"{episode_id}:{platform}"` in task; thread through `_distribute_to_spotify/_apple/_via_webhook`
  - webhook: key as header + `idempotency_key` payload field (keep SSRF pinning/`allow_redirects=False`)
  - pre-check: read episode `with_for_update` in existing session; skip if `distribution[platform].status == "complete"`
  - after success result: locked merge of completion entry (same shape as `on_distribution_complete`); share the merge helper with callbacks.py to avoid drift
- [ ] 4. Full test suite + lint (ruff/mypy) green
- [ ] 5. Deslop scan, third-party review (opencode/GLM pre-PR), PR, demo, CI gate, merge

## Acceptance criteria (from issue)
- Pre-publish check skips platforms already recorded complete (locked read)
- Stable `{episode_id}:{platform}` idempotency key passed to platform API + webhook payload/header
- Success recorded transactionally
