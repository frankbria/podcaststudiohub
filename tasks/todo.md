# #346 — Activate a real pytest warnings policy

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
- [ ] Branch `fix/346-pytest-warnings-policy`
- [ ] TDD: test for `utcnow()` helper (naive, ~now UTC), then implement helper
- [ ] Replace all 62 `datetime.utcnow` refs in src/ and tests/ with the helper
- [ ] Convert `main.py` `@app.on_event("startup")` → lifespan handler
- [ ] Fix content-extraction task tests: patch `_extract_content_async` so no coroutine is created
- [ ] Add `filterwarnings` (error + 3 pydub ignores) to `[pytest]` in `apps/api/pytest.ini`
- [ ] Verify: full suite green with coverage; cold-compile pydub (`rm pydub __pycache__`) still green; ruff clean
- [ ] Deslop → quality gate (opencode pre-PR review) → PR → post-PR review → demo → CI → merge
