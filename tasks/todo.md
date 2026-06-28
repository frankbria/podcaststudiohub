# Issue #300 — P2.2 `on_distribution_complete` silently drops failed distributions

**Branch:** `fix/300-persist-distribution-failures`

## Problem
Permanent distribution errors return `{status: failed}` (Celery treats as SUCCESS) →
`on_distribution_complete` only logs and returns → chain reaches `on_workflow_complete` →
episode marked `complete`. The failure never reaches the DB; episodes look fully published when they aren't.

## Design (settled by CodeRabbit plan — no fork)
Keep distribution tasks returning `{status: failed}` (preserve independent per-platform distribution).
Record each platform outcome; let the final callback derive a distinguishable terminal status.

## Steps (TDD: tests first)
1. **callbacks.py `on_distribution_complete`** — failure branch now persists, via the same locked
   read-modify-write as success: write `generation_progress["distribution"][platform] =
   {status:"failed", error: result.get("error"), failed_at: _utcnow_iso()}`. Do NOT touch
   `generation_status` on failure. Keep the error log.
2. **callbacks.py `on_workflow_complete`** — inline locked RMW: read `distribution`; if any platform
   entry `status != "complete"` set `generation_status="distribution_failed"` and record
   `failed_platforms` in progress; else keep `complete`.
3. **models/episode.py** — add `distribution_failed` to the `generation_status` values comment.
4. **routers/generation.py** — add `distribution_failed` to `_RESTARTABLE_STATUSES`; add it to the
   SSE terminal-break set at ~line 407 (status-consuming surface).
5. **schemas/episode.py** — `generation_status: str` (free-form) — no change.

## Tests (apps/api/tests/unit/test_celery_callbacks.py)
- Replace `test_skips_update_on_failure_result` → `test_persists_failure_on_failure_result`
  (failure is now written, not dropped; `generation_status` unchanged).
- `on_workflow_complete`: sets `distribution_failed` when a platform failed.
- `on_workflow_complete`: stays `complete` when all platforms succeeded.
- (existing `test_marks_episode_complete` with no distribution key still passes.)

## Acceptance criteria
- [x] Non-success writes failure into `generation_progress['distribution'][platform]` and persists.
- [x] Distinguishable terminal state `distribution_failed` introduced.
