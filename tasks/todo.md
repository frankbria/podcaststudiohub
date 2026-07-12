# Issue #316 — Distribution, RSS feed, and analytics frontend surface

Status: IN PROGRESS. Plan source: CodeRabbit comment (adapted). Branch: `feature/issue-316-distribution-analytics-frontend`.

## Key adaptations vs the CodeRabbit plan

- **RSS-first framing (post-#379)**: all connect endpoints are live/ungated, but episode distribution
  to Spotify/Apple defaults to the RSS-feed model (`ENABLE_DIRECT_PLATFORM_PUBLISH=False`). UI presents
  Spotify/Apple as "platforms ingest your RSS feed"; RSS feed generation is the prerequisite
  (422 if `show_title`/`author`/`description` missing from project metadata; 404 on GET = never generated).
- **Spotify OAuth**: `POST /distribution-targets/spotify/authorize` returns JSON `{authorize_url, state}`;
  client does `window.location.href = authorize_url` (proxy strips cross-origin redirects — cannot rely on it).
- **Types**: inline types per page (repo convention); one shared module only for the distribution-target
  shape (`src/lib/types/distribution.ts`) since it's reused by the page + 3 dialogs. No analytics/rss type modules.
- **Envelopes**: distribution list = `{targets, total, page, page_size, total_pages}`; analytics + RSS = bare objects.
  Project rows use `name` (API) → `title` (view-model) mapping per #337/#340 convention.
- **Middleware**: add `'/distribution'` to `PROTECTED_PATHS` in `src/middleware.ts`. No CSP changes needed.
- **No tabs/table/chart primitives exist** — sub-nav is a simple link strip; weekly trend is a simple bar list.
- **Jest**: every new hugeicon must be added to `__mocks__/@hugeicons/core-free-icons.ts`; 80% coverage
  enforced on all four metrics — every new page needs full branch tests (ok / non-ok / reject / empty / mutations).

## Steps

1. **Foundation (nav + middleware + shared types + icon mocks)** — done first, on the branch directly.
   - `src/components/navigation/MainNav.tsx`: add Dashboard + Distribution links (HugeiconsIcon, token classes).
   - `src/middleware.ts`: `PROTECTED_PATHS` += `'/distribution'`.
   - `src/lib/types/distribution.ts`: `DistributionTarget` response shape + list envelope.
   - `__mocks__/@hugeicons/core-free-icons.ts`: pre-add ALL icons used by later steps (avoids parallel conflicts).
   - Tests: `__tests__/components/navigation/MainNav.test.tsx` additions; middleware test if one exists.

2. **Global /distribution page + connect dialogs** (parallel agent A)
   - `src/app/(auth)/distribution/page.tsx`: three-branch render; list targets from
     `GET /api/proxy/distribution-targets`; Cards with platform_name, target_type, is_active Badge,
     token_valid/token_expires_at for Spotify; actions: test (`POST .../{id}/test`), toggle
     (`PUT .../{id}` `{is_active}`), refresh token (`POST .../{id}/refresh-token`, Spotify only),
     delete (ConfirmDeleteDialog → `DELETE .../{id}`). OAuth return query params (`success`/`error`) → toast + refetch.
   - Dialogs in `src/components/dialogs/`: SpotifyConnectDialog (authorize → window.location),
     AppleConnectDialog (authorize instructions → show_id+api_key form), WebhookConnectDialog
     (name + https URL + method/headers). Zod schemas in `src/lib/validation.ts` (apple, webhook).
   - RSS-model note in the UI: connecting Spotify/Apple records distribution; episodes reach platforms via the project RSS feed.
   - Skeleton `src/components/skeletons/DistributionSkeleton.tsx`; EmptyState CTA.
   - Tests: page + dialogs + validation schema cases.

3. **Project RSS feed page** (parallel agent B)
   - `src/app/(auth)/projects/[id]/distribution/page.tsx`: `GET /api/proxy/projects/{id}/rss-feed`;
     404 → EmptyState with Generate CTA; show public_url + copy button, last_generated,
     validation_status; Generate/Regenerate → `POST .../rss-feed/generate` (422 → error toast telling
     user which metadata field is missing); EditPodcastMetadataDialog → `PUT .../rss-feed`
     with `{podcast_metadata: {...}}` (show_title, author, description, category, language, explicit,
     copyright, artwork_url, website_url). Zod schema `podcastMetadataSchema`.
   - Tests: page + dialog.

4. **Project analytics page + project sub-nav** (parallel agent C)
   - `src/app/(auth)/projects/[id]/analytics/page.tsx`: `GET /api/proxy/projects/{id}/analytics?days=N`
     (Select for 7/30/90); summary cards (total_downloads, total_plays, total_listen_hours);
     weekly trend bar-list from `trends.weekly_downloads[{week,downloads}]`; top_episodes list.
   - Sub-nav link strip on `src/app/(auth)/projects/[id]/page.tsx` → Analytics + Distribution (RSS).
   - Skeleton `src/components/skeletons/AnalyticsSkeleton.tsx`.
   - Tests: page + projects page nav additions.

5. **Episode analytics section + event tracking** (parallel agent D)
   - `src/app/(auth)/episodes/[id]/page.tsx`: analytics Card from `GET /api/proxy/analytics/episodes/{id}`
     (metrics, device_breakdown, app_breakdown, top_countries); contained loading + zero-state.
   - `onPlay` on the native `<audio>` → best-effort `POST /api/proxy/analytics/events`
     `{event_type:"play", episode_id, project_id}` (fire-and-forget, swallow errors, fire once per mount).
   - DownloadButton: `onDownloaded?` callback prop; page fires `event_type:"download"`.
   - Tests: episode page + DownloadButton updates.

6. **Integration**: merge worktree branches, full suite (`npm run test:web`), lint, typecheck, coverage.

## Acceptance criteria (from issue)

- [ ] Launch scope confirmed → in scope, build it (CodeRabbit Design Choice 1; #379 settled the model).
- [ ] Distribution page + nav entry exist and work against the live backend contract.
- [ ] RSS feed management surface exists (project-scoped).
- [ ] Analytics pages/sections exist (project + episode).
- [ ] No launch-messaging change needed (feature is now real).
