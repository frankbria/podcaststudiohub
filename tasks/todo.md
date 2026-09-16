# [P1.2] #501 — S3 failures return 422 with bucket and tenant UUIDs in the client-visible body

Branch: `feature/issue-501-s3-failures-503`. Plan source: issue body ("Fix" section), adapted below.

## Findings that shape the plan

- `StorageService.upload_file` wraps boto `ClientError` in a bare `Exception("Failed to upload file to S3: <boto msg>")`
  (`apps/api/src/services/storage_service.py:97`), so every S3 failure reaches the service catch as a plain `Exception`
  carrying bucket/key/tenant text. Never an `OSError`.
- `get_audio_duration` swallows its own errors and returns `None`, so the only non-HTTPException failures inside the
  audio try block are the temp-file write (`OSError`) and the S3 upload.
- Neither service module has a logger today. Add `logging.getLogger(__name__)` (repo convention, e.g. `episode_service.py:27`).

## Steps

1. **RED** — add 4 tests (2 per site) in `tests/test_audio_snippets.py` and `tests/test_content.py`:
   - upload helper `side_effect=Exception("... AccessDenied ... bucket ... content/<tenant>/...")` → 503, fixed detail,
     no bucket/key text in body, boto text present in caplog.
   - upload helper `side_effect=OSError("disk full")` → 422, fixed detail, `"disk full"` not in body.
2. **GREEN** — split the catch at `audio_snippet_service.py:123` and `content_service.py:198`:
   `except (OSError, ValueError)` → 422 fixed message; `except Exception` → `logger.exception(...)` + 503
   `"File storage is unavailable."`. Drop every `str(e)` interpolation at both sites.
3. Full `pytest tests/` + ruff.

## Acceptance criteria (from issue)

- [ ] A storage failure returns 503 with a fixed message; the boto detail is in the server log only
- [ ] A genuine client fault (unwritable temp file, bad value) still returns 422
- [ ] Tests cover both arms at both sites
- [ ] No response body at either site interpolates `str(e)`

## Autonomous decisions

- Tests patch the module-scope upload helper (existing pattern at both sites) rather than boto — the helper is the
  seam the issue names and the outage shape is identical either way.
- 422 detail strings stay close to the old ones ("Failed to process audio file." / "Failed to store PDF.") so
  nothing downstream that greps them changes meaning; only the `str(e)` suffix is gone.
