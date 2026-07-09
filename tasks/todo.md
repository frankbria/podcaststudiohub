# #346 — COMPLETE (PR #348 squash-merged 2026-07-09 as e989616, issue closed)

## Baseline (measured, `uv run pytest -q --no-cov`: 765 passed, 102 warnings)
- `datetime.utcnow()` DeprecationWarning — 62 refs across 29 files (src models/services/utils + tests); model `default=datetime.utcnow` also fires via SQLAlchemy `schema.py`
- FastAPI `on_event` deprecation — `src/main.py:50` (2 warning sources)
- `RuntimeWarning: coroutine '_extract_content_async' was never awaited` — tests patch `asyncio.run` but still build the real coroutine (`tests/unit/test_content_extraction_task.py`)
- Third-party import-time (not fixable in-repo): pydub `audioop` DeprecationWarning, pydub SyntaxWarning (cold compile only), pydub ffmpeg RuntimeWarning (runner without ffmpeg)

## Decisions
- **Policy**: `filterwarnings = error` + targeted ignores for the three pydub third-party warnings only. All first-party warnings get fixed, not ignored.
- **utcnow replacement**: new helper `src/utils/datetime_utils.py::utcnow()` returning **naive UTC** (`datetime.now(timezone.utc).replace(tzinfo=None)`) — columns are `DateTime` without timezone; aware datetimes would break asyncpg writes/comparisons. Not migrating columns to tz-aware (out of scope).
- **Markers**: `unit`/`integration`/`slow` — zero usages in tests (`--strict-markers` already on and green) → stay dropped for good.

## Steps
- [x] Branch `fix/346-pytest-warnings-policy`
- [x] TDD: test for `utcnow()` helper (naive, ~now UTC), then implement helper
- [x] Replace all 62 `datetime.utcnow` refs in src/ and tests/ with the helper (imports normalized to relative in src/)
- [x] Convert `main.py` `@app.on_event("startup")` → lifespan handler
- [x] Fix content-extraction task tests: patch `_extract_content_async` so no coroutine is created
- [x] Add `filterwarnings` (error + pydub ignores, module-scoped, ffprobe variant covered) to `[pytest]`
- [x] Verify: 767 passed / 0 warnings with coverage gate; cold-compile pydub green; ruff clean
- [x] Pre-PR opencode review (no blocking; sweeps verified, ignores scoped) → PR #348 → post-PR review (no blocking; ffprobe fix applied) → demo PASSED (evidence on PR)
- [x] CI green → merged. First CI run exposed that `testpaths = tests tests/unit` made local bare `pytest` run only 767 of 1662 tests; fixed testpaths, swept starlette deprecated status constants, fixed two `asyncio.to_thread` coroutine leaks in wait_for mocks, and enabled ruff W605 (CodeRabbit catch — the pytest.ini comment had overclaimed it). Final: 1655 passed / 7 skipped / 0 warnings.
