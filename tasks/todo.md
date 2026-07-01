# Issue #337 — [P2.4a] Web↔API contract broken (project/episode create + GET /projects 500)

**Branch:** `fix/337-web-api-contract`
**Blocks:** #302 (E2E un-fixme). PLAN_SOURCE: self-authored.

## Canonical decision (the architectural fork, resolved with a safe default)

The **API is the source of truth**; the DB column is `name` and episodes store nested
`episode_metadata`. So:

1. **Projects use `name`** (not `title`) end-to-end; the web app conforms (UI copy can still
   say "Title", but the data field / payload is `name`).
2. **Episodes use nested `episode_metadata.{title,description}`** end-to-end; the web app reads
   nested and sends nested.
3. **Create-time metadata is lightweight.** Relax `ProjectCreate`/`EpisodeCreate` validators so
   they don't demand fields the product doesn't collect at create (`show_title`, `author`,
   episode `description`). Server auto-defaults `podcast_metadata.show_title = name` when absent so
   RSS has a sensible value. The existing **distribution-time** gate
   (`rss_generation_service.REQUIRED_METADATA_FIELDS`) is untouched — completeness is enforced
   where it actually matters.

Rationale for not stopping: DB/RLS/all other consumers already use `name`; changing the DB is
high-risk and pointless. This is the lower-risk, single-source-of-truth direction.

## Steps (TDD: RED → GREEN per step)

### Backend
- [ ] **B1. Fix `GET /projects` 500.** Write a failing integration test that seeds one project for
      an authed user and calls `GET /projects`; read the real traceback. Candidates: count-subquery
      `select(func.count()).select_from(query.subquery())`, ORM serialization after
      `commit()` (missing `refresh`/`expire_on_commit`), or RLS GUC unset on the async session.
      Fix the actual root cause. Add the regression test. (`services/project_service.py`,
      `routers/projects.py`, tests)
- [ ] **B2. Relax `ProjectCreate.validate_podcast_metadata`** — only type-check keys that are
      present; drop the "required + non-empty" demand for `show_title`/`author`/`description`.
      Default `show_title` to `name` in `create_project` when absent. Keep `ProjectUpdate` in sync.
      Tests for: minimal metadata create succeeds; show_title defaulted.
- [ ] **B3. Relax `EpisodeCreate.validate_episode_metadata`** — require `title` (non-empty),
      make `description` optional. Keep `EpisodeUpdate` in sync. Tests.

### Frontend
- [ ] **F1. Project `title` → `name`.** Update web `Project` interfaces + all read sites
      (`dashboard/page.tsx` 205/217/219/226/234, `projects/[id]/page.tsx` 267/268,
      `EditProjectDialog.tsx`), create payload (`dashboard/page.tsx:85`), update payloads
      (`dashboard/page.tsx:118`, `projects/[id]/page.tsx:145`). Send
      `podcast_metadata:{show_title:name, language, explicit}`. Keep form input id `#project-title`
      + "Title" UI label so E2E selectors still resolve.
- [ ] **F2. Episode nested metadata.** In `projects/[id]/page.tsx`: Episode interface + list reads
      (304/316/317/324/332) → `episode.episode_metadata.title/description`; create payload
      (114) → `{project_id, episode_metadata:{title}}`; edit payload (174) →
      `{episode_metadata:{title}}`. (`episodes/[id]/page.tsx` already correct.)
- [ ] **F3. Update web unit tests + `lib/validation.ts` only if shape assertions break.** Jest.

### E2E (un-fixme the handed-off specs)
- [ ] **E1.** Remove `.fixme` from: `02-projects.spec.ts:289` (Project isolation),
      `03-episodes.spec.ts:341` (Episode isolation), `10-integration.spec.ts:12` (Complete Journey)
      + `:324` (Concurrent Workflow). Helpers already use two independent sessions (PR #338) and
      fill `#project-title`/`#episode-title` — no helper change expected.

### Verify / gates
- [ ] Backend `uv run pytest` green; web `npm run test` + typecheck green; lint.
- [ ] Demo the create→list→display round-trip (Phase 11 hard gate) — projects + episodes.
- [ ] E2E specs green (or documented dev-env dependency if they need the deployed target).

## Acceptance criteria mapping
- AC1 (align contract) → F1/F2/B2/B3. AC2 (GET /projects 500 + test) → B1.
- AC3 (round-trip verify) → demo. AC4 (un-fixme 4 specs) → E1.
