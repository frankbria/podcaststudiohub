# #308 — Episode delete orphans S3 audio; no tenant-offboarding / GDPR erasure path

**Plan source**: self-authored (no plan comment on issue), derived from code exploration 2026-07-09.
**Branch**: `feature/issue-308-episode-delete-s3-erasure`

## Design decisions (made autonomously — no architectural fork)

1. **Erasure entry point = self-service `DELETE /auth/me`** (204, `Depends(get_current_user)`).
   The system has no admin/superuser role (`User` has only `is_active`/`is_verified`), so an
   admin-only endpoint isn't possible; user-initiated deletion is the standard GDPR
   right-to-erasure shape and matches existing hard-delete endpoints.
2. **S3 deletion is key-based, not prefix-listing.** IAM intentionally does NOT grant
   `s3:ListBucket` (deployment/README.md:318). Every S3 object has its key stored in a DB row
   (`episodes.s3_key`, `episode_compositions.composed_s3_key`, `audio_snippets.s3_key`,
   `rss_feeds.s3_key`, content-source `source_data['s3_key']`), so we collect keys from rows
   before deleting them. No new StorageService list/bulk API needed — iterate `delete_file`
   (S3 `delete_object` is already idempotent on missing keys).
3. **S3/local cleanup is best-effort** (log warning, never block the DB delete) — copies the
   existing `delete_audio_snippet` pattern (audio_snippet_service.py:286-318).
4. **Wrap sync `delete_file` in `asyncio.to_thread`** at async call sites (matches how
   `upload_file`/`download_file` are handled; existing `delete_file` call is bare — leave that).
5. **Tests fake StorageService with unittest.mock patches** — the repo's established S3 test
   convention (tests/unit/test_storage_service.py, test_episodes.py:1691).

## Steps (TDD)

- [x] 1. Branch off main: `feature/issue-308-episode-delete-s3-erasure`.
- [x] 2. **Episode delete cleanup** — `apps/api/src/services/episode_service.py:delete_episode`:
  - RED: tests in `tests/test_episodes.py`: (a) delete of episode with `s3_key` calls
    `StorageService.delete_file(s3_key)`; (b) no `s3_key` → no S3 call; (c) S3 delete raising
    still deletes the DB row (204); (d) local `file_path`/`transcript_path` files removed
    (tmp_path fixture); (e) composition `composed_s3_key` also deleted.
  - GREEN: collect episode.s3_key + its EpisodeComposition.composed_s3_key; best-effort
    delete S3 objects (`asyncio.to_thread(storage.delete_file, key)`, try/except → log
    warning); best-effort `os.remove` of `file_path`, `transcript_path`,
    `composed_file_path`; then `db.delete(episode)` + commit.
- [x] 3. **Tenant offboarding** — new `apps/api/src/services/offboarding_service.py` +
  `DELETE /auth/me` in `src/routers/auth.py`:
  - RED: new `tests/test_offboarding.py`: register user via `/auth/register`, seed
    project/episode (with s3_key, composition) /audio_snippet/rss_feed rows; patch
    StorageService; `DELETE /auth/me` → 204; `delete_file` called once per collected key;
    user + cascaded rows + billing rows gone; the old token now 401/403 on `/auth/me`.
  - GREEN: `erase_user(db, user)`: collect S3 keys from episodes, compositions, snippets,
    rss feeds, content-source `source_data['s3_key']`; collect local paths; best-effort
    delete S3 + local files; explicitly delete `BillingSubscription`/`BillingUsage` by
    `user_id` (no FK — DB cascade won't reach them); `db.delete(user)` (FK CASCADE removes
    projects → episodes → content_sources/compositions, snippets, rss_feeds, distribution
    targets, templates, tts configs, layouts, team memberships/invitations); commit; return
    summary counts. Router endpoint is a thin wrapper.
  - RLS note: runs as the requesting user with tenant context armed, so RLS permits deleting
    own-tenant rows. If the `users` RLS policy blocks self-delete, stop and report (don't
    improvise a bypass).
- [x] 4. **Docs reconcile**:
  - `deployment/README.md:315`: `s3:DeleteObject` rationale → "remove audio when an episode
    or account is deleted" (now true).
  - Add "Tenant offboarding / GDPR erasure" section (deployment/README.md): what
    `DELETE /auth/me` erases (Postgres rows + S3 objects + local artifacts), key-based
    deletion rationale (no ListBucket), limitations below.
- [x] 5. Quality gates: full pytest 1689 passed / diff-cover 98% / ruff clean; deslop done;
  internal review (1 Major rebutted: S3-before-commit ordering is deliberate — see #366);
  cross-family opencode/GLM round 1 REQUEST_CHANGES → fixes (password step-up, 409
  mid-generation guard, core user DELETE, audit log, rate limit) → round 2 APPROVE;
  mutation checks: 4 killed, 1 infeasible (billing cascade DB-enforced, documented): full pytest from apps/api (`uv run pytest tests/`), ruff, coverage ≥85;
  deslop; internal review + cross-family (opencode/GLM) review; PR; demo; CI; merge.

## Acceptance criteria (from issue)

- [x] `StorageService.delete_file(episode.s3_key)` called on episode delete (idempotent on
  missing) and local file artifacts removed.
- [x] Documented tenant-offboarding routine erasing Postgres rows + all S3 audio for a user.
- [x] deployment/README.md reconciled with actual behaviour.

## Known limitations (disclose in PR)

- `Team` rows have no owner; erasure removes the user's memberships/invitations but leaves
  team shells.
- Stripe-side customer data is not touched (only local billing rows) — out of scope here.
- Content-source uploads are deleted on account erasure but not on single-episode delete
  (episode delete scope per AC = episode audio + local artifacts + composition audio).
