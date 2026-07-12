# Issue #313 — Wire the audio-composition timeline (P4.1) — SHIPPED via PR #375

Status: merged 2026-07-11 as 6ea063c. Follow-up: #376 (download S3-backed
snippets to the worker so they actually compose).

## Problem (verified against current code)

- `routers/generation.py:309-317` dispatches `generate_podcast_task` with
  `enable_composition` but never `composition_timeline` → defaults to `None`.
- `podcast_generation.py:417` forwards it to `build_generation_workflow`, which
  passes `composition_timeline or []` into `merge_audio_snippets_task.si` (line 850).
- `audio_composition.py:49-82`: empty timeline → `AudioSegment.empty()` exported
  → zero-length silent MP3 replaces the generated audio at upload (composed file
  is `final_audio_path`).
- `tests/unit/test_audio_composition_task.py:110` codifies the bug
  (`test_empty_timeline_returns_success`).

## Plan adaptations vs CodeRabbit plan

1. `audio_snippet_service.get_audio_snippets` is **async** (AsyncSession); Celery
   uses `SyncSessionLocal`. Resolver does its own sync `select(AudioSnippet)` query.
2. `AudioSnippet.file_path` stores the **S3 key** when S3 is configured (see
   `upload_audio_snippet`), so a snippet file may not exist on the worker's disk.
   Resolver includes only snippets whose `file_path` is a local file; skips others
   with a warning. S3-snippet download = documented Known Limitation / follow-up.
3. Empty-timeline `ValueError` raised **before** the merge task's try block so it
   propagates (deterministic error — retrying is pointless) and the chain's
   `link_error` (`on_workflow_failure`) marks the episode failed.

## TDD checklist

- [x] RED: invert `test_empty_timeline_returns_success` → `pytest.raises(ValueError)`;
      add resolver unit tests (ordering, always-includes-main, skips-missing-file,
      never-empty, degrades-to-main-only on DB error); add workflow test asserting
      `build_generation_workflow` receives a non-empty timeline with the generated
      audio as `main_content` when composition is enabled and no timeline supplied.
- [x] GREEN: guard in `merge_audio_snippets_task` (before try);
      `resolve_composition_timeline(db, project_id, audio_file_path)` in
      `podcast_generation.py` — project snippets ordered intro/music → main_content
      → outro/midroll/ad/other, each entry `{file_path, segment_type}`; wire into
      `generate_podcast_task`'s existing episode-load block (caller-supplied
      timeline wins; resolution failure degrades to `[main]`, never empty).
- [x] Full pytest + ruff + coverage gates; review; PR; demo; CI; merge.

## Known limitations

- Snippets stored only in S3 (no local file) are skipped, not downloaded.
- Timeline resolved on the generation worker; assumes chain tasks share a host
  filesystem (same assumption the existing chain already makes for
  `final_audio_path`).
