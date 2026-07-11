# Issue #372 — Test isolation: mocked-podcastfy workflow tests poison psycopg Jsonb adaptation

## Root cause (verified with import-audit diagnostic)

`unittest.mock.patch.dict(sys.modules, {...})` restores the dict on exit by
**clearing it and re-applying the snapshot** — evicting every module imported
*during* the window, not just the patched keys. The first poisoning test in
`tests/test_celery_workflow.py` lazily imports the entire `psycopg` tree
(~80 modules incl. the `psycopg_binary` C extension) inside the window;
eviction + later re-import creates a new `psycopg.types.json.Jsonb` class that
psycopg's already-registered adapters map (held by the previously imported
SQLAlchemy dialect) doesn't recognize → `cannot adapt type 'Jsonb'`.

Diagnostic evidence: audit-hook plugin showed test 1 of `TestFullWorkflowChain`
evicts all `psycopg*` modules at patch exit.

Same pattern exists in 5 more files (24 call sites total):
`tests/test_celery_workflow.py` (9), `tests/unit/test_podcast_generation_task.py` (5),
`tests/unit/test_audio_composition_task.py` (4), `tests/unit/test_task_retry.py` (5),
`tests/unit/test_generation_idempotency.py` (1).

## Plan (TDD)

- [x] RED: `tests/test_sync_jsonb_isolation.py` — sync-session ORM flush of a
      `User` row (JSONB `encrypted_api_keys`); file sorts after
      `test_celery_workflow.py`. Confirm it FAILS after workflow tests, PASSES alone.
- [x] GREEN: add `tests/module_patching.py` with `patch_modules(mapping)` — a
      context manager that sets the given `sys.modules` keys and on exit restores
      **only those keys** (leaving modules imported during the window intact).
      Replace all 24 `patch.dict(sys.modules, ...)` sites with it.
- [x] Verify: issue repro commands pass in both orders; full API test suite green;
      ruff clean.

## Scope note

Fixing all 6 files (not just test_celery_workflow.py) — identical latent bug,
mechanical swap, per bug-ownership rule.
