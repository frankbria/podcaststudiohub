# Issue #310 — TZ-aware analytics params vs naive DB timestamps

## Adapted plan (approved autonomously — no architectural fork)

Most of the issue is already fixed: PR #348 introduced the naive `utcnow()` helper
(`src/utils/datetime_utils.py`) and analytics/RSS/usage services already use it, so the
deprecated `datetime.utcnow()` calls and the write-side timestamps are done.

**Remaining bug:** `analytics_service.get_episode_analytics` uses caller-supplied
`date_from`/`date_to` directly in the WHERE clause against naive
`AnalyticsEvent.created_at`. A `Z`-suffixed query param arrives TZ-aware from FastAPI →
asyncpg raises "cannot compare timestamp with/without time zone".
(`get_project_analytics` only uses naive internal bounds — not affected.)

## Steps

- [x] RED: `test_get_episode_analytics_tz_aware_date_range` failed with the exact
      asyncpg DataError from the issue.
- [x] GREEN: shared `to_naive_utc()` helper in `datetime_utils.py`; used in
      `get_episode_analytics` and `episode_service` date filters.
- [x] GLM pre-PR review: APPROVE. Took its two minor suggestions: shared helper
      (also fixes pre-existing non-UTC-offset bug in episode_service) and
      load-bearing +03:00 offset tests (analytics + episodes).
- [x] Gates all passed — SHIPPED via PR #369 (1701 tests + coverage gate, GLM APPROVE pre+post-PR + CI review no-defects, live demo verified, CI green, squash-merged, issue #310 closed).
