# Issue #271 — Restrict episode/project update to user-editable fields (mass-assignment)

Branch: `advisor/005-restrict-update-mass-assignment`
Plan source: issue body + `plans/005-restrict-update-mass-assignment.md` (no drift vs defc572)

## Key adaptation vs the written plan
The plan assumed only the Celery pipeline (`tasks/callbacks.py`) writes system fields and
that nothing internal uses `update_episode`. **Two internal callers actually write system
fields through `update_episode`:**
- `script_generation_service.py:220` → `transcript_path`
- `quality_metrics_service.py:193` → `generation_progress` — **already broken**: calls
  `update_episode(db, episode_id, {dict})` but the signature is `(db, episode, EpisodeUpdate)`;
  `dict.model_dump()` would raise in production (only passes today because the test mocks it).

So a blanket allowlist on `update_episode` would silently drop these legitimate writes.
Adaptation: give the pipeline a dedicated `set_episode_system_fields()` writer and reserve
`update_episode` (allowlisted) for the public endpoint. This also fixes the latent bug.

## Steps (TDD)
- [ ] **Schema** `schemas/episode.py`: `EpisodeUpdate` keeps only user-editable fields —
      `episode_number`, `episode_metadata`, `tts_config_id`, `template_id`. Remove
      `generation_status`, `generation_progress`, `s3_key`, `s3_url`, `duration_seconds`,
      `file_size_bytes`, `file_path`, `transcript_path`, `task_id`, `task_started_at`,
      `task_completed_at`.
- [ ] **episode_service.py**: add `EPISODE_USER_EDITABLE_FIELDS` constant; filter in
      `update_episode` (defense-in-depth). Add `set_episode_system_fields(db, episode, **fields)`
      internal helper.
- [ ] **script_generation_service.py:220-221**: write `transcript_path` via
      `set_episode_system_fields`.
- [ ] **quality_metrics_service.py:193**: write `generation_progress` via
      `set_episode_system_fields` (fixes broken signature).
- [ ] **project_service.py**: add `PROJECT_USER_EDITABLE_FIELDS` allowlist + filter in
      `update_project`. `ProjectUpdate` schema unchanged (all 6 fields are user-editable).
- [ ] **Tests**: episodes — PUT system fields ⇒ columns unchanged; user-editable update works.
      projects — allowlist holds; normal update works. Update `test_quality_metrics` for the
      new `set_episode_system_fields` call. Confirm `test_script_generation` still passes.
- [ ] Verify: `uv run pytest tests/ -k "episode or project or quality or script" -q` + `ruff check .`
- [ ] Update `plans/README.md` status row.

## Out of scope (unchanged)
`tasks/**` (sync Celery writers via `_update_episode`), DB columns, auth/ownership.
