# #376 — Composition: download S3-backed snippets to the worker before merging

**Plan source**: self-authored (no plan comment on the issue). **Approved autonomously** — no architectural fork: the issue sanctions doing the download in `resolve_composition_timeline` *or* the merge task; the merge task is chosen so download, use, and cleanup live in one task with a `finally` (no tempfile lifetime across Celery task boundaries).

## Current behavior (verified in code)

- `upload_audio_snippet` stores the S3 key in `AudioSnippet.file_path` (and in `s3_key`) and deletes the upload tempfile → snippets are never on worker disk (`audio_snippet_service.py:142`).
- `resolve_composition_timeline` (`podcast_generation.py:107`) skips any snippet whose `file_path` isn't a local file → timeline degrades to main-only; snippets never play.
- `merge_audio_snippets_task` (`audio_composition.py`) consumes `segment["file_path"]` blindly.

## Changes

### 1. `src/tasks/podcast_generation.py` — `resolve_composition_timeline`
- For a snippet whose `file_path` is a local file: unchanged (local entry).
- Else, if `snippet.s3_key` and `settings.AWS_S3_BUCKET` are set: emit `{"s3_key": ..., "segment_type": ...}` instead of skipping.
- Else: skip with warning (unchanged).
- Update the "none are on local disk" summary log / ponytail comment accordingly.

### 2. `src/tasks/audio_composition.py` — `merge_audio_snippets_task`
- Before the merge loop, resolve each segment to a local path:
  - `file_path` exists on disk → use it.
  - has `s3_key` → download via sync `boto3.client("s3").download_file(settings.AWS_S3_BUCKET, key, tmp)` to a `NamedTemporaryFile` (consistent with `upload_to_s3_task`); on any download failure, log a warning and **skip the segment** (degrade — never fail the chain; worst case timeline is main-only).
  - neither usable → current behavior (unchanged for plain-file segments: missing main content still fails/retries).
- Track downloaded temp paths; delete them in `finally` (covers success, failure, and retry paths).

### 3. Tests (TDD — write first)
- `tests/unit/test_podcast_generation_task.py::TestResolveCompositionTimeline`:
  - S3-backed snippet (s3_key set, bucket configured) → included as `s3_key` entry, ordered correctly.
  - s3_key set but no bucket → skipped.
  - no local file and no s3_key → skipped (update existing `_snippet` helper with `s3_key`).
- `tests/unit/test_audio_composition_task.py`:
  - s3 segment downloaded (mock boto3), merged, tempfile removed on success.
  - download failure → segment skipped, merge still succeeds with remaining segments (main-only worst case), no chain failure.
  - tempfiles removed on merge failure path.

## Acceptance criteria mapping
- Composed episode contains intro → main → outro (duration-verified) → demo in Phase 11.
- Download failure degrades, doesn't fail the chain → per-segment skip (strictly gentler than full main-only degrade).
- Temp cleanup success + failure paths → `finally` block + tests.
- Unit tests for download/degrade/cleanup → above.

## Out of scope
- No change to snippet upload, callbacks, or chain structure.
- Router-supplied timelines (file_path-only entries) behave exactly as before.
