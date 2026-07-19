# Issue #321 — [P5.5] Blocking synchronous boto3 calls in async handlers (self-authored plan)

Plan source: self-authored (no plan comment on the issue).
Verified against `main` @ `1b3d76c`, 2026-07-19.

## Verified current state (issue line refs re-checked against live code — they drifted)

| Issue claim | Verdict | Evidence |
|---|---|---|
| Download handler calls `head_object` synchronously | TRUE | `apps/api/src/routers/episodes.py:407-413` (issue said :362) |
| Download handler calls `get_object` synchronously | TRUE | `episodes.py:434-446` ×2 (range + non-range; issue said :389-398) |
| `StorageService.delete_file` calls boto3 directly in `async def` | TRUE | `apps/api/src/services/storage_service.py:132-146` → `delete_object` at :140 |
| `StorageService.file_exists` calls boto3 directly in `async def` | TRUE | `storage_service.py:177-195` → `head_object` at :188 |
| `upload_file`/`download_file` already offloaded | TRUE | `storage_service.py:82-98`, :114-130 — `await asyncio.to_thread(...)` is the established idiom |

In-scope blocking calls: exactly the 4 above (`head_object`×2, `get_object`×2, `delete_object`×1).
Confirmed NOT in scope (verified by full sweep of `apps/api/src`):
- `storage_service.py:164` `generate_presigned_url` — CPU-only local signing, no network I/O; existing convention leaves it sync.
- `episodes.py:415` `os.path.getsize` — local filesystem stat, not network-bound.
- `tasks/audio_composition.py`, `tasks/s3_upload.py` — plain sync Celery tasks, no event loop.
- Every other S3 touch point already goes through the offloaded wrappers.

Callers that benefit with no change needed: `rss_feed.py:313` (public audio route → `file_exists`),
`audio_snippet_service.py:309` (`delete_file`), `tasks/maintenance.py:150` (`asyncio.run` → `delete_file`).

## Steps (TDD: tests first, RED)

1. **Tests (RED) — storage service** — extend `apps/api/tests/unit/test_storage_service.py`:
   - `delete_file` offloads: patch `asyncio.to_thread` with an AsyncMock whose side_effect invokes the
     func synchronously; assert awaited once with `service.s3_client.delete_object` and
     `Bucket`/`Key` kwargs; assert `delete_object` itself was NOT called directly on the mock's thread path.
   - `file_exists` offloads: same pattern for `service.s3_client.head_object`.
   - Existing behavior tests (`test_delete_file_success`, `test_file_exists_*`) must keep passing unchanged
     (plain MagicMock survives `to_thread`).

2. **Implement storage service** — `storage_service.py`:
   - `delete_file`: `await asyncio.to_thread(self.s3_client.delete_object, Bucket=..., Key=...)`
   - `file_exists`: `await asyncio.to_thread(self.s3_client.head_object, Bucket=..., Key=...)`
   - Reuse the verbatim idiom + comment style from `upload_file`/`download_file`
     ("boto3 is synchronous; run it off the event loop …"), citing `#321`. 4-space indent file.

3. **Tests (RED) — download endpoint** — extend `apps/api/tests/test_download_endpoint.py`:
   - Wrap `client.get(.../download)` in `patch("asyncio.to_thread", side_effect=<async passthrough>)`;
     assert it was awaited for `head_object` and `get_object` (≥2 awaits, bound methods of the mocked
     `s3_client` as first arg).
   - Existing download tests (full/range/local-file/404/403/416) must keep passing unchanged.

4. **Implement router** — `episodes.py` (tab-indented file — preserve tabs):
   - Add `import asyncio`.
   - `head_response = await asyncio.to_thread(storage.s3_client.head_object, Bucket=..., Key=...)`
   - Both `s3_response = storage.s3_client.get_object(...)` → `await asyncio.to_thread(storage.s3_client.get_object, ...)`
   - Keep `iter_s3_body` streaming unchanged (it already offloads per-chunk reads via `to_thread`,
     `download_utils.py:180-198`).

5. **Gates** — `cd apps/api && uv run pytest tests/` (coverage ≥85), `ruff check .`, deslop scan,
   opencode/GLM review pre-PR, demo per AC, PR, post-PR review, CI, docs sync, merge.

## Acceptance criteria checklist
- [ ] AC1 All network-bound boto3 calls in async paths wrapped in `await asyncio.to_thread(...)`
      (steps 2, 4 — the 4 verified call sites)
- [ ] AC2 No new sync boto3 calls in async paths (step 5 — grep sweep in quality gate +
      reviewer checklist item)

## Autonomous decisions (no architectural fork)
- **`asyncio.to_thread` over presigned-URL redirect.** The issue sanctions both; `to_thread` is the
  listed-first option and the minimal change. A 302 redirect would change endpoint semantics (auth is
  checked once at redirect time, URL then reusable), drop server-side Range handling, and force rewriting
  the existing download test suite. The streaming path already offloads chunk reads — only the initial
  HEAD/GET block. Not a fork: safe default exists.
- **`generate_presigned_url` left sync** — CPU-only (no network); matches existing code's own convention
  and the issue's "network-bound" wording.
- **Fix `StorageService` internals rather than every caller** — `rss_feed.py:313` and
  `audio_snippet_service.py:309` are fixed for free; no call-site churn.
- **Tests assert offload via patched `asyncio.to_thread`** rather than timing-based event-loop probes —
  deterministic, no flaky sleeps.

## Risks / notes
- `filterwarnings = error` is live (#348) — no new warnings tolerated.
- Coverage gate ≥85% (#345) — the new tests add branches, not uncovered code.
- `episodes.py` uses tabs; `storage_service.py` uses 4 spaces — preserve each file's style.
- `patch("asyncio.to_thread")` patches the module globally for the duration of the test — acceptable in
  test scope; ensure passthrough side_effect so the handler body still executes.
