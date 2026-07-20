# Issue #322 — [P5.6] Backend performance: N+1 team counts, inline external URL HEAD blocking creates, per-event analytics commits, unindexed episode search (self-authored plan)

Plan source: self-authored (no plan comment on the issue; CodeRabbit "Create Plan" checkbox unchecked).
Verified against `main` @ `5d0da07`, 2026-07-19.

## Verified current state (issue line refs re-checked against live code)

| Issue claim | Verdict | Evidence |
|---|---|---|
| N+1 COUNT per team on list, no pagination cap | TRUE | `apps/api/src/routers/teams.py:55-63` loops `_team_response` (:32-36) → `team_service.get_member_count` per team (`team_service.py:109-117`); `get_teams_for_user` (:75-83) has no limit |
| `create_content_source` awaits external HEAD, ≤4 hops × 10s | TRUE | `apps/api/src/routers/content.py:96-107` calls `SourceValidatorService.validate_by_type` synchronously → `validate_url_source` (`source_validator_service.py:238-257`) → `_check_url_accessibility` (:112-198): ≤4 sequential HEADs, 10s each |
| Analytics track: 2 validation SELECTs + commit + refresh per event | TRUE | `apps/api/src/routers/analytics.py:47-62` (2 SELECTs) → `analytics_service.py:24-58` `db.add`/`commit`/`refresh` |
| Leading-wildcard JSONB ILIKE, no usable index, no created_at index | TRUE | `apps/api/src/services/episode_service.py:165-173` `ilike("%term%")` on `episode_metadata['title'/'description'].astext`; existing GIN is `jsonb_path_ops` (containment-only, migration 002); `idx_episodes_title` btree can't serve leading wildcard; no `created_at` index; `pg_trgm` unused in repo |

Key leverage found during exploration:
- `extract_content_task` already runs on every create (`auto_extract=True` default) and `extract_from_url` **re-fetches the URL itself** with strict SSRF-safe pinned GET — the create-time HEAD is a redundant fail-fast pre-check for the default path.
- Codebase background idiom is Celery (no in-process buffering anywhere). Task dispatch from routers is always try/except "broker down must never fail the request".
- RLS precedent for workers: `billing_service.py:277-280` arms tenant context on a non-request session; `analytics_events` has FORCE RLS (migration 014) so a worker-side insert must `set_tenant_context(tenant_id)`.
- Grouped-COUNT idiom already exists in `analytics_service.py:80-86`.
- Migration pattern for indexes on populated tables (issue #318): `autocommit_block()` + `DROP INDEX IF EXISTS` + `postgresql_concurrently=True` (see `005_add_fk_indexes.py:39-47`); latest migration is `017`, next is `018`.

## Steps (TDD: tests first, RED)

1. **Tests (RED) — teams bulk counts + list cap**
   - `apps/api/tests/unit/test_team_service_unit.py`: tests for new `get_member_counts(db, team_ids)` — grouped counts, active-only, teams with zero active members absent from dict; and `count_teams_for_user`.
   - `apps/api/tests/test_teams.py`: list with multiple teams returns correct `member_count` per team; with `team_service.get_member_count` (singular) patched to raise, list still returns 200 (proves no per-team COUNT); `limit`/`offset` honored; `total` reflects full count beyond the page.

2. **Implement teams** — `team_service.py`: add `get_member_counts` (grouped `func.count()` on `team_members`, `team_id.in_(...)`, `status == "active"`, mirroring `analytics_service.py:80-86`), `count_teams_for_user`, and `limit`/`offset` params on `get_teams_for_user`. `routers/teams.py`: list endpoint gains `limit: int = Query(100, ge=1, le=500)`, `offset: int = Query(0, ge=0)`; one teams query + one total COUNT + one grouped member-count query (constant 3 queries); build responses from the counts dict. Keep `_team_response`/`get_member_count` for single-team endpoints. No migration (`team_members.team_id` already indexed).

3. **Tests (RED) — URL reachability off the request path**
   - `apps/api/tests/unit/test_source_validation.py` (**tabs** — preserve): `validate_url_source` no longer performs HEAD (mocked `httpx.AsyncClient` never called); format/SSRF failures still raise `URLValidationError`. Keep/adjust direct `_check_url_accessibility` tests (method stays, used by the background task).
   - `apps/api/tests/test_content.py`: GAP-015 unreachable/timeout/redirect-loop creates now return **201** (contract change per AC); assert `extract_content_task.delay` still dispatched for `auto_extract=True`; assert new `validate_url_reachability_task.delay` dispatched when `source_type='url'` and `auto_extract=False`; SSRF/format 422s unchanged.

4. **Implement URL validation change** — `source_validator_service.py`: `validate_url_source` runs format + SSRF only; `_check_url_accessibility` kept for the task. `src/tasks/content_extraction.py` (module already in worker `include`): add `validate_url_reachability_task` (sync wrapper + `asyncio.run` impl on `celery_async_session`, per file idiom): run `_check_url_accessibility`; on failure set `extraction_status='failed'` + `error_message`; on success leave `pending`. `routers/content.py`: after insert, when `source_type == 'url'` and `auto_extract` is False, dispatch it (lazy import, try/except log — never fail creation). Sweep for other `validate_by_type` callers (e.g. content update endpoint) and apply the same behavior.

5. **Tests (RED) — analytics queued**
   - `apps/api/tests/test_analytics.py`: patch the new task; assert 201 body still carries `id`, `created_at`, `event_metadata`; assert task dispatched with full payload (incl. `tenant_id`); 404 validation behavior unchanged; update any round-trip tests that read events back after tracking (seed directly or run the task body inline).
   - New `apps/api/tests/unit/test_analytics_track_task.py`: worker task inserts `AnalyticsEvent` with the given id/created_at, arms `set_tenant_context(tenant_id)` before insert, commits once, does not retry on `IntegrityError`.

6. **Implement analytics queue** — `analytics_service.py::track_event`: build the event payload (id=`uuid4()`, `created_at=utcnow()`, hashed IP, device/app detection, `tenant_id`) with **no DB write**, return payload. New `src/tasks/analytics.py` (register in `worker.py` `include` + `task_routes`): `track_analytics_event_task` — `celery_async_session()` + `set_tenant_context(tenant_id)` → insert → single commit; retry ×3 backoff on transient errors, no retry on `IntegrityError`. `routers/analytics.py`: keep the 2 validation SELECTs (preserves 404 contract), dispatch in try/except (broker down → log, still 201), return `AnalyticsEventResponse` built from the payload. `refresh` gone everywhere.

7. **Tests (RED) — migration 018 unit test** — `apps/api/tests/unit/test_migration_018_episode_search_indexes.py` (importlib-load by path, mock `alembic.op`, per `test_migration_005/006` convention): assert `CREATE EXTENSION IF NOT EXISTS pg_trgm`; two GIN `gin_trgm_ops` expression indexes on `(episode_metadata->>'title')` and `(episode_metadata->>'description')`; one btree on `created_at`; all three inside `autocommit_block()` with `DROP INDEX IF EXISTS` rerun guards + `postgresql_concurrently=True`; downgrade drops them.

8. **Implement migration 018** — `apps/api/alembic/versions/018_episode_search_indexes.py` following `005_add_fk_indexes.py` pattern. Apply locally with `alembic upgrade head` so integration tests run against the migrated DB.

9. **Gates** — `cd apps/api && uv run pytest tests/` (coverage ≥85), `ruff check .`, deslop scan, opencode/GLM cross-family review pre-PR, demo per AC (Showboat), PR with Known Limitations, post-PR review, CI green + feedback triage, docs sync, merge.

## Acceptance criteria checklist
- [x] AC1 Member counts batched in one grouped query + list size capped (steps 1–2) — `get_member_counts`/`count_teams_for_user` + `limit`/`offset` Query params; regression test patches singular `get_member_count` to raise
- [x] AC2 URL reachability moved to background; create does inline format/SSRF validation only (steps 3–4) — `validate_url_source` drops HEAD; `validate_url_reachability_task` for `auto_extract=False`; unreachable create now 201
- [x] AC3 Analytics events queued; per-event commit off the request path; `refresh` dropped (steps 5–6) — `build_event_payload` (no DB write) + `track_analytics_event_task`; response built from in-process id/created_at
- [x] AC4 `pg_trgm` + GIN indexes on episode_metadata title/description expressions and btree on `created_at` (steps 7–8) — migration 018; EXPLAIN confirms `idx_episodes_metadata_title_trgm`/`_description_trgm` (Bitmap Index Scan) and `idx_episodes_created_at` (Index Scan) are used

## Autonomous decisions (no architectural fork)
- **`pg_trgm` GIN over full-text search.** AC lists pg_trgm first with FTS as "(or …)" alternative; pg_trgm preserves the exact current substring-match semantics (FTS would change tokenization/ranking behavior and API-visible results). Safe default.
- **Celery queue for analytics** over in-process buffering or an outbox table. Celery is the only background idiom in this codebase (generation, extraction, RSS refresh all use it); in-process buffers lose events on restart and have no precedent. Trade-off accepted per the codebase's own rule ("broker down must never fail the request"): a broker outage loses queued events with a logged warning — analytics are already fire-and-forget from the frontend (`apps/web/.../episodes/[id]/page.tsx:582`). Will be disclosed in PR Known Limitations.
- **Keep the 2 request-side validation SELECTs on track.** The hazard is the write path (commit+refresh); the SELECTs preserve the 404 contract and tenant-scoped validation. Only the INSERT moves to the worker.
- **Response contract preserved on track (201 + id/created_at/event_metadata)** by generating `id`/`created_at` in-process — no DB read needed to answer.
- **Reachability for `auto_extract=False` URLs** gets a lightweight `validate_url_reachability_task` (placed in the already-included `content_extraction` task module — zero worker config change); the default `auto_extract=True` path is covered by extraction's existing re-fetch, so no double-fetch.
- **422→201 contract change for unreachable URLs** is mandated by the AC ("inline only format/SSRF validation"); failure now surfaces as `extraction_status='failed'` + `error_message`. Existing GAP-015 tests encoding the old contract get updated.
- **`TeamListResponse.total` becomes the true full count** (one cheap COUNT query) so the cap is usable by a pagination UI; `limit` default 100 / max 500 keeps the current response shape and passes existing tests (`total==0/2` cases stay valid).

## Risks / notes
- Tests require local PostgreSQL (`TEST_DATABASE_URL`, role `podcastfy_app`) with migrations applied — check `pg_isready` and run `alembic upgrade head` before pytest.
- `filterwarnings = error` and `--strict-markers` live; coverage gate ≥85%.
- Indentation: `test_source_validation.py` and parts of `test_content.py` use tabs; `team_service.py` uses 4 spaces — preserve each file's style.
- Worker-side analytics insert runs under FORCE RLS — must `set_tenant_context` (missing setting → NULL → WITH CHECK failure), precedent `billing_service.py:277-280`.
- `test_migration_metadata.py` compares table sets only — index-only migration needs no model change.
- New Celery task module `src/tasks/analytics.py` must be added to `worker.py` `include` or the worker never registers it.
