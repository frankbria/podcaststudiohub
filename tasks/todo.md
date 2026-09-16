# [P2.5] #490 — Flaky `test_list_pagination_page_size`: root cause + deterministic paging

Branch: `feature/issue-490-flaky-pagination-tiebreak`. Plan source: self-authored (issue has DoD, no plan comment).

## Root-cause findings (Phase 2)

- **Order dependence is structurally impossible for this test.** Every registered user gets its own
  `tenant_id` (uuid4) and `audio_snippets` is under FORCE RLS, so rows from other tests cannot appear in
  this user's list. `test_audio_snippets.py` is also the *first* module in the issue's `-k` selection, so no
  earlier module can poison process state. And the test only asserts `len <= 2`, `page == 1`,
  `page_size == 2` — leaked rows could not fail it anyway.
- **Non-deterministic ordering cannot fail this test either** (it never inspects order). But the list
  query *is* non-deterministic: `order_by(AudioSnippet.created_at.desc())` with no tiebreak, and
  `created_at` is a `DateTime` default that can tie. With LIMIT/OFFSET, Postgres gives no stable order
  for equal keys across queries, so a paging client can see duplicates/skips. That is the real product
  defect the issue asked to rule out, and it gets fixed.
- **The one observed failure has no surviving traceback.** The only assertions that *can* fail are the
  fixture's `201` and the list's `200`, i.e. a non-2xx response. PR #486's body records that the same
  session was under system memory pressure (two full-suite runs OOM-killed). Reproduction attempts here:
  42 runs of the exact selection + 1 instrumented run (`-X dev`, `PYTHONASYNCIODEBUG=1`, GC-time warnings
  surfaced) → 0 failures, 0 warnings; and the test has never failed in CI (7 non-dependabot failed runs
  grepped). Conclusion: environmental, not logic. The test also swallowed the five upload status codes, so
  a failed upload (e.g. a DB connection fault) would have surfaced only as the later `200` assertion —
  which is exactly the shape of the report.

## Steps

1. **RED** — rewrite `test_list_pagination_page_size` to prove paging: assert every upload is `201`,
   force all five `created_at` values to tie, page through with `page_size=2`, assert page sizes 2/2/1,
   no overlap, union == uploaded ids, and a deterministic order (id desc within the tie). Fails on `main`
   because ties currently come back in heap order.
2. **GREEN** — `get_audio_snippets`: `order_by(created_at.desc(), id.desc())`. One line.
3. Verify 20 consecutive runs of the issue's full selection.
4. Follow-up issue (Phase 13): `project_service.get_projects` and `episode_service` list sort have the
   same missing tiebreak.

## Acceptance criteria (issue DoD)

- [ ] Root cause identified (order dependence vs non-deterministic ordering) — see findings above
- [ ] Non-deterministic ordering → deterministic tiebreak in the list query (product fix)
- [ ] Test made self-diagnosing / self-isolating (asserts uploads, proves paging)
- [ ] Test passes across ≥20 consecutive runs of the full selection

## Autonomous decisions

- Tiebreak column is `id` (UUID, PK) — always unique, no migration. No new index: the table has no
  `created_at` index today and the issue does not ask for one.
- Scope stays on `audio_snippets`; the projects/episodes tiebreaks are filed, not bundled.
