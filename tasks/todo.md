# Issue #378 — [P4.3.1] First Spotify/Apple distribution fails until the project RSS feed is generated

Status: SHIPPED — merged 2026-07-12 via PR #384 (squash); issue #378 closed. Follow-ups filed: #382 (feed regen on completion), #383 (UI enable_distribution), #385 (feed public-read policy).

Plan source: self-authored. Branch: `feature/issue-378-rss-preflight-distribution` (deleted).

Post-plan addition (PR review round): the pre-flight runs under a SAVEPOINT (`begin_nested`) so DB failures (unique-RSSFeed race) degrade to skip+warning instead of poisoning the 'queued' commit.

## Design decision (autonomous — no architectural fork)

The issue offers Option 1 (auto-generate the feed before distribution; flagged as expensive because
the Celery task is sync and `RSSGenerationService` is async) and Option 2 (pre-flight check/warn,
recommended as cheaper). Key finding: the sync-bridge cost only exists inside the Celery task — the
**generation router** (`apps/api/src/routers/generation.py`) is async and already resolves active
distribution targets before dispatch. So the cheap path is a router pre-flight that:

1. **Auto-generates** the feed when possible (project metadata valid) — one awaited service call,
   no new infrastructure. Feed with zero complete episodes is valid RSS.
2. **Skips Spotify/Apple + returns a clear warning** when auto-generation is impossible (missing
   `show_title`/`author`/`description` → `ValueError`) or errors (S3 down) — mirroring the existing
   graceful-skip precedents (no S3 bucket, no active targets), instead of a guaranteed
   `distribution_failed`.

This satisfies both halves of the acceptance criterion ("no guaranteed first-attempt failure, OR
clearly told beforehand").

## Steps

1. **Backend pre-flight (TDD)** — `apps/api/src/routers/generation.py`
   - After the `platforms` dict is built: if `spotify`/`apple_podcasts` present and
     `not settings.ENABLE_DIRECT_PLATFORM_PUBLISH`, check `RSSGenerationService.get_rss_feed()`.
   - No feed / no `public_url` → `await generate_rss_for_project(db, project_id, user.id)`.
   - On any exception: log warning, drop spotify/apple from `platforms`, collect a warning string.
   - Response: additive `warnings: [...]` key (only when non-empty) on the 202 payload.
   - Tests: `apps/api/tests/test_distribution_wiring.py` (existing file covers router→platforms
     wiring): (a) no feed + valid metadata → feed auto-created, spotify kept, no warnings;
     (b) no feed + missing metadata → spotify dropped, warning returned, still 202;
     (c) feed exists → no regeneration; (d) webhook-only → no pre-flight;
     (e) `ENABLE_DIRECT_PLATFORM_PUBLISH=True` → no pre-flight.

2. **Frontend warning surface (TDD)** — `apps/web/src/app/(auth)/episodes/[id]/page.tsx`
   - Generate handler (~line 482): if the 202 response has `warnings`, show them (toast/notice).
   - Test: extend `apps/web/__tests__` episode page test with a warnings-response case.

3. **Follow-up issue** — the RSS feed is never regenerated when an episode completes, so
   Spotify/Apple never see new episodes until a manual regenerate. Out of scope here; file as
   `[P4.3.2]`.

## Acceptance criteria

- [x] Project with valid podcast metadata: adding a Spotify/Apple target + generating an episode
      does NOT produce a first-attempt `distribution_failed` (feed auto-generated at kickoff).
- [x] Project without metadata: user is clearly told (API warning surfaced in UI; platforms
      skipped, episode generation still proceeds).
- [x] Existing feed / webhook-only / direct-publish-flag paths unchanged.

## Known limitations (by design, noted for PR)

- The warning is returned in the API response and shown as a toast; it is not persisted in
  `generation_progress` (that dict is overwritten at dispatch and managed by worker callbacks).
- Feed staleness (new episode not in the feed) is pre-existing and tracked by the follow-up issue.
