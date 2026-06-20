# Issue #220 — Celery/SSE reliability fixes (apps/api)

Plan source: CodeRabbit comment (adapted to current code). Branch: `fix/220-celery-sse-reliability`

## Fix 1 — Inline S3 upload bypasses retries (`tasks/podcast_generation.py` ~404)
- `upload_to_s3_task(...)` is called as a plain function inside `finalize_episode_generation_task`.
  Called directly, its `self.retry` raises immediately → upload's own retry never runs.
- Wrap the inline call in an explicit retry loop: up to 3 attempts, `calculate_backoff` + `time.sleep`
  between tries. Retry on transient exception AND on a returned `status != "success"`.
- On exhaustion: mark episode `failed` + return failed dict (matches existing upload-failure branch;
  avoids double-retry against the finalize task's own outer `self.retry`).
- Add `import time`.

## Fix 2 — Wrong status in `on_upload_complete` (`tasks/callbacks.py:95`)
- Remove `"generation_status": "uploading"` from the `_update_episode` updates dict.
- Keep `s3_url`, `s3_key`, and progress updates.
- Update test `test_updates_episode_s3_url_on_success` (asserts status == "uploading").

## Fix 3 — SSE leaks DB session (`routers/generation.py:337-357`)
- `event_generator` loops `await db.refresh(episode)` on the request-scoped session; on client
  disconnect the session can be left non-idle.
- Capture `episode_id` before the generator; per iteration open `async with AsyncSessionLocal()`
  and `session.get(Episode, episode_id)`.
- Wrap loop to catch `asyncio.CancelledError` (disconnect) + log; `finally` for cleanup.
- Add `AsyncSessionLocal` import.

## Verification
- `uv run pytest tests/unit/test_celery_callbacks.py tests/unit/test_podcast_generation_task.py tests/test_sse_auth.py`
- New tests: upload-retry-then-fail path; on_upload_complete no longer sets status; SSE uses fresh session.
- Demo (Phase 11), CI gate (Phase 12), then PR + merge.
