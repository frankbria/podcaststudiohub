# Issue #309 — Wrong transcript_path persisted; engine artifacts never cleaned up

Plan source: CodeRabbit comment on issue, adapted to current code (post-#367).
Autonomous decisions (no architectural fork):
- `transcript_path=None` (not captured-real-path): the run dir is deleted after upload, so a captured path would dangle exactly like the fabricated one.
- Output routing via `conversation_config["text_to_speech"]["output_directories"]` — verified podcastfy 0.4.1 deep-merges this (`NestedConfig.configure` recurses), so other TTS defaults are preserved. No new kwarg to `generate_podcast()`.
- Composition chain: raw run-dir artifacts cleaned in `on_composition_complete` (the only place that still knows the pre-composition `file_path` before overwriting it); the uploaded composed file is already cleaned by `upload_to_s3_task`.
- Failure paths: best-effort `rmtree` of the current attempt's run dir on soft-timeout/retry/exhaustion so failed attempts don't leak either.
- No-S3 dev path: clean the run dir after `_persist_local_audio` copies the audio out.

## Steps

- [ ] 1. Tests first (RED):
  - `tests/unit/test_podcast_generation_task.py`: success result has `transcript_path is None`; `generate_podcast()` receives `conversation_config` with `text_to_speech.output_directories.{audio,transcripts}` under `tempfile.gettempdir()`; user-supplied `conversation_config` keys preserved; keep `output_dir`-not-passed guard.
  - `tests/test_s3_upload.py` (TestTempFileCleanup): uploading a file inside a `podcastfy-run-*` dir removes the whole dir (audio + transcript); a run-dir-named dir outside temp root is untouched; plain temp files behave as before.
  - `tests/unit/test_celery_callbacks.py`: `on_composition_complete` removes the old run-dir artifacts before persisting the composed `file_path`.
- [ ] 2. `src/tasks/s3_upload.py`: add `GENERATION_RUN_DIR_PREFIX = "podcastfy-run-"`; extend `_cleanup_temp_file` to rmtree the containing run dir (prefix match, under temp root) instead of just the file.
- [ ] 3. `src/tasks/podcast_generation.py`: create `run_dir = tempfile.mkdtemp(prefix=GENERATION_RUN_DIR_PREFIX)` before calling the engine; inject output_directories into a copied `conversation_config`; set `transcript_path=None`; rmtree run dir on failure paths; clean run dir after `_persist_local_audio` in the no-S3 branch (guard `_persist_local_audio` for retry-safety: return dest if dest exists and source is gone).
- [ ] 4. `src/tasks/callbacks.py`: `on_composition_complete` — read old `file_path`, `_cleanup_temp_file(old_path)` best-effort, then update as today.
- [ ] 5. Full api test suite + ruff; quality gates; PR.

## Acceptance criteria

- [ ] `Episode.transcript_path` never points at a non-existent fabricated path (set to None).
- [ ] Engine audio/transcript artifacts are written to a per-run temp dir and deleted after successful S3 upload (both finalize and workflow-chain paths).
- [ ] Persistent (non-temp) paths can never be deleted by cleanup.

## Known limitations (for PR body)

- On workflow *failure*, the run dir of the failed attempt inside the chain may remain until OS temp cleanup (bounded; regeneration uses a fresh dir).
- Episode transcript content is not retained anywhere after this change (it never was retrievable — the stored path was fabricated).
