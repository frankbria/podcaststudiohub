# Issue #325 — Populate `country` on analytics events (P6.2 / P3)

Branch: `fix/325-populate-analytics-country`. Plan verified against current code.

**Problem:** `top_countries` always `[]` because `country` is never written. The
column, read-side `GROUP BY country` aggregation, and `EpisodeAnalyticsResponse`
schema all already exist — only the write path has a gap.

**Plan is stale:** CodeRabbit's plan targets a `track_event` service function, but
issue #322 (PR #415) moved ingestion to `build_event_payload` → payload dict →
`track_analytics_event_task` → `AnalyticsEvent` insert. So `country` must thread
through **4** places, not 3 (the plan missed the Celery task insert).

**Design choice (resolved, no fork):** CDN/edge country header (`CF-IPCountry`,
fallback `X-Country`), normalized. No new deps, no migration, no MaxMind DB
lifecycle. Matches existing `X-Forwarded-For` header-reading pattern and the P3
polish scope. Graceful `NULL` when no header present.

## Tasks
- [ ] `models/analytics_event.py`: add `normalize_country()` helper (trim,
      uppercase, reject empty + Cloudflare sentinels `XX`/`T1` → `None`).
- [ ] `services/analytics_service.py`: `build_event_payload` gains `country`
      param; payload stores `normalize_country(country)`.
- [ ] `routers/analytics.py`: read `CF-IPCountry` then `X-Country`, pass through.
- [ ] `tasks/analytics.py`: set `country=payload.get("country")` on the insert.
- [ ] Tests (TDD): unit for `normalize_country`; payload includes normalized
      country; task insert sets country; route threads header → queued payload.

## Acceptance criteria (from issue)
Populate `country` via CDN country header in the ingestion path so `top_countries`
returns real data. ✔ satisfied by the populate path (vs. the "drop" alternative).
