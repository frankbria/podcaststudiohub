# Issue #385 — [P4.3.4] RSS feed public_url returns S3 AccessDenied

Status: SHIPPED — merged 2026-07-13 via PR #390 (squash, a25b5a2); issue #385 closed.
All gates green: backend 1810/1810 (+7 skip), coverage 94.52% (diff 100%), ruff clean,
full CI 12/12 incl. review bot (no defects). Demo 4/4 criteria with outcome evidence
against real Postgres (FORCE RLS) + real S3, incl. 403 AccessDenied contrast on the old
S3 URL. Reviews: opencode (GLM) APPROVE pre-PR and post-PR (posted to PR), internal
APPROVE. Follow-up filed: #391 (P4.3.6, episode enclosure URLs are private S3 URLs).
Plan was self-authored (no plan comment on the issue).

**DEPLOY ACTION REQUIRED**: staging's hand-managed apps/api `.env` must set
`API_PUBLIC_BASE_URL=https://dev.podcaststudiohub.me/api` or regenerated feeds will
store `http://localhost:8000/...` URLs. Existing rows keep the stale S3 URL until
regenerated (generate/PUT/#382 auto-refresh).

## Problem

`RSSFeed.public_url` stores the raw S3 URL
(`https://{bucket}.s3.{region}.amazonaws.com/rss-feeds/{project_id}/feed.xml`).
The bucket is ACL-disabled with no public-read policy, so the URL returns
AccessDenied — the whole RSS distribution model (#315) is dead end-to-end.

**Worse (found in exploration):** the existing public endpoint
`GET /feeds/{project_id}/podcast.xml` (`src/routers/rss_feed.py:219`) is itself
broken for real unauthenticated callers: it reads `rss_feeds` via `get_db` with
no tenant context, and FORCE RLS (`tenant_id = current_setting('app.tenant_id',
true)::uuid`, migration 003/014) yields zero rows → 404 for everyone. Existing
tests mock `RSSGenerationService`, so they never caught it.

## Decision (autonomous, per issue's own recommendation)

**Option B** — serve feeds through the API's public endpoint and store that URL
as `public_url`. No AWS bucket-policy change (Option A rejected: infra change
outside the repo, and it would make private-bucket posture inconsistent).

Sub-decisions:
- New setting `API_PUBLIC_BASE_URL` (no existing API-base setting; `FRONTEND_URL`
  is the Next.js app). Default `http://localhost:8000`.
- Fix the public endpoint's RLS problem by **removing the tenant-scoped DB read**:
  the s3_key is deterministic (`rss-feeds/{project_id}/feed.xml`), so download
  straight from S3 and 404 when the object doesn't exist. Lazy + correct; avoids
  a SECURITY DEFINER migration. UUIDs are unguessable; feeds are public by design.
- Keep the S3 upload + refresh hook (#382) as the content store. NOT switching the
  endpoint to render fresh XML from DB — that would need RLS-bypassing reads of
  episodes/projects (scope creep; freshness is already handled by rss_refresh).

## Steps

1. **Config**: add `API_PUBLIC_BASE_URL: str = "http://localhost:8000"` to
   `src/config.py`; add to `apps/api/.env.example` and root `.env.example`.
2. **StorageService.download_file** (`src/services/storage_service.py:96`):
   raise `FileNotFoundError` on ClientError 404/NoSuchKey instead of generic
   `Exception`, so callers can distinguish missing objects.
3. **Public endpoint** (`src/routers/rss_feed.py:219-297`): drop the
   `get_rss_feed` DB read; build `s3_key` deterministically; return 404 on
   `FileNotFoundError`, 500 on other storage errors. Remove now-unused `db` /
   `rss_service.get_rss_feed` usage (keep service dep for `.storage`).
4. **public_url construction** (`src/services/rss_generation_service.py`
   `_upload_rss_to_s3`/`_update_rss_feed` ~357/421): set
   `public_url = f"{settings.API_PUBLIC_BASE_URL.rstrip('/')}/feeds/{project_id}/podcast.xml"`.
   Refresh task (#382) and distribution metadata pick this up automatically.
5. **Tests (TDD — write first)**:
   - `tests/test_rss_feed.py`: public endpoint 200 serves S3 bytes without any
     DB row (proves the RLS fix); 404 when S3 object missing; fixture
     `make_mock_rss_feed` URL updated; generate-endpoint asserts new
     `public_url` format.
   - `tests/unit/test_rss_generation_service.py`: `public_url` = API URL, not
     the `upload_file` return; s3_key unchanged.
   - storage unit test: download 404 → `FileNotFoundError`.
6. **Docs/env**: `deployment/README.md` note — staging must set
   `API_PUBLIC_BASE_URL` to the nginx-exposed API origin.

## Acceptance criteria

- [x] `public_url` stored for new/regenerated feeds is the API endpoint URL,
      not the S3 URL.
- [x] `GET /feeds/{project_id}/podcast.xml` returns the feed XML with
      `application/rss+xml` to a fully unauthenticated client, with a real
      RLS-enabled DB (no mocked service on the success path).
- [x] Missing feed → 404 (not 500, not AccessDenied).
- [x] Distribution metadata (`rss_feed_url`) carries the fetchable API URL.
- [x] Backend suite green, coverage gate (85%) green, lint green.
