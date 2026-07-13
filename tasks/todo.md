# Issue #382 — [P4.3.2] RSS feed is never regenerated when an episode completes

Status: IN PROGRESS — implementation + review fixes committed; quality gates green
(1805 passed full suite pre-fix run; diff coverage 100%; 5/5 mutation checks killed;
opencode APPROVE; internal Critical fixed). Awaiting final full-suite run, then PR.
Branch: `feature/issue-382-rss-regen-on-complete`

## Post-plan additions (review round)

- **Critical (internal review, empirically confirmed)**: asyncio.run + shared pooled
  async engine fails on the 2nd call per worker process ("Future attached to a different
  loop"). Fixed with `celery_async_session()` in database.py — per-call NullPool engine,
  disposed after use. Applied to rss_refresh AND content_extraction (same latent bug).
- **Major**: finalize's refresh call sat inside the retry-bearing try; a refresh escape
  would self.retry and eventually mark a completed episode failed. Now locally guarded +
  regression test.
- Skipped (nitpick, moot): finalize reads episode ids after commit — safe, both session
  factories set expire_on_commit=False.

## Problem

`RSSGenerationService.generate_rss_for_project` is only called from the RSS router and the
#378 generation pre-flight. When an episode reaches `complete`, nothing regenerates the feed,
so Spotify/Apple keep ingesting a stale (often empty) feed XML on S3.

## Design decisions (made autonomously — no architectural fork)

- **Post-completion hook, not a chain stage.** The issue floats both. A feed-refresh chain
  stage only covers the chain path (`build_generation_workflow`); the finalize path
  (`finalize_episode_generation_task`, used when composition+distribution are both off)
  never invokes the chain or `on_workflow_complete`. A shared hook called from **both**
  completion sites covers everything; a chain stage cannot.
- **Sync→async bridge**: `asyncio.run()` + `AsyncSessionLocal`, same pattern as
  `content_extraction.py:101` / `maintenance.py:150`. Celery sessions don't arm the tenant
  GUC; the service filters by explicit `project_id`, which is the existing task-side pattern.
- **Gate on an existing RSSFeed row** (`get_rss_feed`). If no feed row exists, no platform is
  consuming the feed yet — the #378 pre-flight creates it at distribution time. Regenerating
  unconditionally would fail on projects with incomplete `podcast_metadata` for no benefit.
- **Only on `complete`.** On `distribution_failed` the episode's `generation_status` is not
  `complete`, so `_get_completed_episodes` wouldn't include it anyway — regeneration is a no-op.
- **Never fail the completion callback.** The hook catches and logs all exceptions
  (mirrors the #378 pre-flight's non-fatal handling). Regeneration is already idempotent:
  single upsert per project, service commits internally.

## Steps

1. **Add `refresh_project_rss_feed(project_id, user_id)` helper** in
   `apps/api/src/tasks/rss_refresh.py` (new small module; avoids callbacks↔podcast_generation
   import tangle). Opens `AsyncSessionLocal` via `asyncio.run`, skips (log) if
   `get_rss_feed` returns None, else `await generate_rss_for_project(db, project_id, user_id)`.
   Swallows + logs every exception. Returns True/False (regenerated or not) for tests.
2. **Call it from `on_workflow_complete`** (`src/tasks/callbacks.py:379` success branch only):
   capture `episode.project_id` / `episode.user_id` inside the session
   (expire_on_commit=False, but capture anyway before session close), invoke the helper after
   `db.commit()` / session close.
3. **Call it from `finalize_episode_generation_task`** (`src/tasks/podcast_generation.py:773`
   path): after the successful `db.commit()` that marks `complete` (not on the StaleDataError
   absorb branch — episode was deleted), using captured project/user ids.
4. **Tests (TDD — write first)**:
   - `tests/unit/test_rss_refresh.py`: helper regenerates when feed row exists; skips when
     none; swallows service exceptions (ValueError on bad metadata) and returns False.
   - `tests/unit/test_celery_callbacks.py`: on_workflow_complete triggers refresh on success;
     does NOT trigger on distribution_failed; missing episode → no refresh; refresh error
     doesn't break the callback.
   - `tests/test_celery_workflow.py`: finalize task triggers refresh after marking complete;
     no refresh on failed S3 upload.
5. **CI fix (user-requested, same PR)**: `deploy-dev.yml:77` and `:87`
   `JWT_SECRET_KEY: test-jwt-secret-for-ci` (22 bytes) → `test-jwt-secret-for-ci-0000000000`
   (33 bytes, same value `test.yml:80` already uses). PyJWT emits InsecureKeyLengthWarning
   below 32 bytes; the repo's `filterwarnings=error` turns every `jwt.encode` into a 500, which
   is why "Deploy to Development" has failed on every recent main push (164 failed / 417 errors,
   all rooted in `POST /auth/register` 500). Also align `playwright-tests.yml:151`/`:183`
   for consistency (server-mode, warning-only today, but same latent trap).

## Acceptance criteria

- [ ] Episode completing via the workflow chain regenerates the project RSS feed (feed XML on
      S3 includes the new episode).
- [ ] Episode completing via the finalize path (no composition/distribution) regenerates too.
- [ ] Projects without an RSS feed row are untouched (no error, no feed created).
- [ ] A regeneration failure never fails/marks-failed the episode completion.
- [ ] Deploy to Development workflow's "Run API tests" step passes (JWT key fix).
