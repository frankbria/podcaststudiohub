# Issue #315 — Spotify/Apple direct-publish targets are not real publishing APIs

Plan source: CodeRabbit comment (adapted). Branch: `fix/315-rss-distribution-default`.

## Adapted plan

1. **Config flag**: add `ENABLE_DIRECT_PLATFORM_PUBLISH: bool = False` to `apps/api/src/config.py`
   (next to `ENABLE_PLATFORM_DISTRIBUTION`), plus `.env.example` entry if the other flags have one.
2. **RSS feed URL resolution in the task** (`apps/api/src/tasks/platform_distribution.py`):
   small helper `_rss_feed_url_for_project(db, project_id)` querying `RSSFeed.public_url` via the
   already-open sync session; inject as `episode_metadata["rss_feed_url"]` when platform is
   spotify/apple_podcasts.
3. **RSS-default distribution**: in `_distribute_to_spotify` / `_distribute_to_apple`:
   validate `show_id` as today; when `settings.ENABLE_DIRECT_PLATFORM_PUBLISH` is False (default),
   skip credentials/token/publish entirely and return
   `{"status": "success", "method": "rss_feed", "platform_episode_id": None,
     "platform_url": <rss_feed_url>, "rss_feed_url": ..., "error": None}`.
   Missing `rss_feed_url` → raise `ValueError` with an actionable message (permanent failure, no
   retry, no false success). Flag on → existing direct-publish path unchanged.
4. **Docstrings**: mark `publish_episode` in `spotify_service.py` / `apple_podcasts_service.py` as
   experimental/unverified; state RSS is the supported ingestion mechanism.
5. **Tests** (`apps/api/tests/unit/test_platform_distribution_services.py`, TDD):
   - Service-level: assert `mock_client.post.call_args` — exact endpoint URL, Authorization header,
     Idempotency-Key, JSON body fields (both services).
   - Task-level default (flag off): `publish_episode` NOT called; result has method=rss_feed,
     feed URL as platform_url, platform_episode_id None. Missing feed URL → ValueError.
   - Flag on: `publish_episode` called once with correct kwargs (existing success tests updated to
     enable the flag — behavior-change adaptation, disclosed in PR).
   - `TestRetryClassification` unchanged.

## Autonomous decisions / deviations from the CodeRabbit plan

- **No lazy feed generation** in the resolver. The distribution task is sync (Celery,
  `SyncSessionLocal`); `RSSGenerationService` is fully async. Bridging asyncio+S3+metadata
  validation into the worker for a convenience path isn't warranted — the issue's own acceptance
  criteria says "RSS already generated". Missing feed → clear, actionable permanent failure
  ("generate the project's RSS feed first"), never a fake success.
- **Result envelope keeps `status: "success"`, distinguishes via `method: "rss_feed"` +
  `platform_episode_id: None`**, not a new top-level status. `record_platform_distribution` and
  `on_workflow_complete` treat any per-platform status ≠ "complete" as failure, and
  `episodes.generation_status` has a DB CHECK constraint (migration 016) — a new status value would
  need a migration + callback rewrite for zero user benefit. The RSS result is genuinely successful.
- **No UI/schema messaging changes**: web status types are free `string` with fallbacks; the
  distribution entry's `platform_url` becomes the RSS feed URL, which is the honest actionable link.

## Acceptance criteria

- [ ] Verified against current platform APIs: Spotify/Apple ingest via RSS, not direct POST
      (documented in service docstrings; direct path no longer default).
- [ ] Spotify/Apple targets pivot to the RSS-feed model by default.
- [ ] Direct-publish gated behind explicit default-off flag and clearly marked experimental.
- [ ] Tests assert the actual outbound request URL/headers/body.
- [ ] No silent false-positive success when no RSS feed exists.
