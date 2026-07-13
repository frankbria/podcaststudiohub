# #391 — [P4.3.6] RSS `<enclosure>` URLs embed private S3 URLs

Status: IN PROGRESS — plan approved autonomously (no architectural fork; issue itself
recommends the 302-presign endpoint, option 1).

## Problem
`_build_episode_item` embeds `episode.s3_url` (private bucket → AccessDenied) in
`<enclosure url>`. Feed XML is fetchable since #385, but platforms can't download audio.

## Approach (mirrors #385)
Public unauthenticated API endpoint that 302-redirects to a per-request presigned S3 URL
(fresh presign every fetch → no expiry problem; S3 target handles Range natively).

**Forced adaptation vs the issue's sketched path**: episode audio key is
`podcasts/user-{user_id}/episode-{episode_id}.mp3` (`build_podcast_s3_key`, #215) and
`episodes` is FORCE RLS — an unauthenticated request has no tenant context, so no DB
read is possible (#385 precedent). The URL must carry what the key derivation needs:
`GET /feeds/episodes/{user_id}/{episode_id}/audio.mp3`
`user_id` is already public in today's raw S3 enclosure URLs — no new exposure.

## Steps (TDD)
1. RED: tests
   - service: enclosure URL is `{API_PUBLIC_BASE_URL}/feeds/episodes/{user_id}/{id}/audio.mp3`
     when `episode.s3_key` is set; falls back to legacy `s3_url` behavior when not.
   - router: 302 with Location = presigned URL, no auth, no DB read (only storage patched);
     404 when object missing; 500 hides internals.
2. GREEN:
   - `rss_generation_service.py`: build API enclosure URL in `_build_episode_item`.
   - `rss_feed.py`: new `public_router` route → derive key via `build_podcast_s3_key`,
     `file_exists` → 404, `generate_presigned_url(key, 3600)` → 302 RedirectResponse,
     `Cache-Control: no-store`.
   - `public_router` already registered in main.py:134 — nothing to wire.
3. Gates: pytest tests/ (CI parity), ruff, coverage ≥85, third-party review pre-PR + post-PR,
   demo with outcome evidence, CI green, docs sync, merge.

## Acceptance criteria
- AC1: generated feed XML contains API enclosure URLs, not raw S3 URLs.
- AC2: GET audio endpoint (no auth) → 302 to a presigned URL that actually serves the object.
- AC3: missing object → 404; S3 errors → generic 500.
- AC4: fresh presign per request (long-lived feed stays valid).
