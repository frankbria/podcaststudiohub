# Issue #490: root-cause the flaky pagination test and make audio-snippet paging deterministic

*2026-09-16T20:35:34Z*

PR #531. The issue asked which of two causes made `test_list_pagination_page_size` fail once in ~6 local runs: test-order dependence (rows leaking between tests) or non-deterministic paging (an unstable sort). This demo shows why neither can fail the test as it was written, what the real defect in the list query is, the one-line fix, and the 20-run verification the issue requires. Everything runs against the real app stack and the local Postgres under the non-superuser `podcastfy_app` role, so RLS is enforced exactly as in production.

**Criterion 1, root cause.** Order dependence first: every registered user is its own tenant, and `audio_snippets` is under FORCE ROW LEVEL SECURITY, so another test's rows cannot appear in this user's list.

```bash
grep -n "tenant_id = uuid4()" src/services/auth_service.py; grep -n "audio_snippets" alembic/versions/003_force_rls.py
```

```output
292:        tenant_id = uuid4()
36:	'audio_snippets',
```

The test module is also the first one collected in the issue's exact `-k` selection, so no earlier module can poison process state either.

```bash
uv run pytest tests/ --co --no-cov -p no:cacheprovider -k "audio_util or snippet or duration" 2>/dev/null | grep -E "<Module" | head -3
```

```output
    <Module test_audio_snippets.py>
    <Module test_episode_layouts.py>
    <Module test_episodes.py>
```

And the assertions the test used to make on `main` could not be failed by leaked rows *or* by an unstable order. It never asserted the five uploads, never inspected order, and only checked `len <= 2`. The only things that could fail were the two status codes, which is what an environmental fault looks like, and PR #486 records that the reporting session was under memory pressure.

```bash
git show main:apps/api/tests/test_audio_snippets.py | sed -n "554,560p"
```

```output
	# Request page with size 2
	response = await client.get("/audio-snippets?page=1&page_size=2", headers=auth_headers)
	assert response.status_code == 200
	data = response.json()
	assert len(data["snippets"]) <= 2
	assert data["page"] == 1
	assert data["page_size"] == 2
```

**Criterion 2, the product defect.** The list query ordered by `created_at desc` alone. Postgres gives tied keys no stable order under LIMIT/OFFSET, so a client paging a list with ties can get a row twice or never. The fix adds the primary key as the tiebreak.

```bash
git diff main...HEAD -- src/services/audio_snippet_service.py | grep "^[-+]" | grep -v "^+++\|^---"
```

```output
-	# Get paginated results ordered by creation date descending
-	query = query.offset(skip).limit(limit).order_by(AudioSnippet.created_at.desc())
+	# Newest first; id breaks created_at ties so LIMIT/OFFSET pages never
+	# duplicate or skip a row (Postgres gives tied keys no stable order) (#490).
+	query = (
+		query.offset(skip)
+		.limit(limit)
+		.order_by(AudioSnippet.created_at.desc(), AudioSnippet.id.desc())
+	)
```

Live proof through the real API: register a user, upload five snippets, force all five `created_at` values to tie (as the app role, under RLS), then fetch three pages of size 2. The contract a client relies on is: page sizes 2/2/1, five distinct ids, every uploaded id seen exactly once, deterministic order within the tie.

```bash
PYTHONPATH=. DATABASE_URL="postgresql+asyncpg://podcastfy_app:podcastfy_app_password@localhost:5432/podcastfy" uv run python /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/1cef615c-c510-4340-8d7c-e7430dfcd7e6/scratchpad/demo_490.py 2>&1 | grep -v "\"level\": \"INFO\"\|\"level\": \"WARNING\""
```

```output
uploaded 5 snippets, all 201
created_at tied on 5 rows
{"page": 1, "total": 5, "total_pages": 3, "created_at": ["2026-01-01T19:00:00Z"], "ids": ["94a2f8d6-9826-40d9-ab6d-6ff6c6537003", "759a52ea-6aa6-4922-bc83-a24b1b419f3c"]}
{"page": 2, "total": 5, "total_pages": 3, "created_at": ["2026-01-01T19:00:00Z"], "ids": ["6c77a7e2-3066-43d2-a5e3-2ff2776d064e", "693fefb2-31e2-408f-ae68-8b6cccca96de"]}
{"page": 3, "total": 5, "total_pages": 3, "created_at": ["2026-01-01T19:00:00Z"], "ids": ["4c8559d2-7b74-4582-977f-11b24c94a320"]}
page sizes: [2, 2, 1]
distinct ids across pages: 5 of 5 uploaded
order is id desc within the tie: True
PAGING CONTRACT: HOLDS
```

**Criterion 3, the test now catches the defect.** The rewritten test forces the tie and asserts exact page sizes, no duplicate or skipped row, and a deterministic order. Run it against `main`'s version of the service to show it fails there, at the order assertion and nowhere else (the uploads and the page-size checks all pass).

```bash
git checkout main -- src/services/audio_snippet_service.py && uv run pytest tests/test_audio_snippets.py::test_list_pagination_page_size -q --no-cov -p no:cacheprovider --tb=line 2>&1 | grep -E "AssertionError|passed|failed" | grep -v "^E " | head -3; git checkout HEAD -- src/services/audio_snippet_service.py && git status --short src/ && echo "service restored to HEAD"
```

```output
/home/frankbria/projects/podcaststudiohub/apps/api/tests/test_audio_snippets.py:590: AssertionError: assert ['7a525db9-ce...1092225e17ca'] == ['e719f734-ee...3cba5c344ab3']
============================== 1 failed in 0.35s ===============================
service restored to HEAD
```

Same test against this branch:

```bash
uv run pytest tests/test_audio_snippets.py::test_list_pagination_page_size -q --no-cov -p no:cacheprovider 2>&1 | tail -1
```

```output
============================== 1 passed in 0.36s ===============================
```

**Criterion 4, 20 consecutive runs.** The issue's exact selection (`pytest tests/ -k "audio_util or snippet or duration"`, 130 tests), run 20 times back to back on this commit. Each line is one full run of the selection.

```bash
cat /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/1cef615c-c510-4340-8d7c-e7430dfcd7e6/scratchpad/verify20_summary.txt; echo "green runs: $(grep -c "rc=0" /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/1cef615c-c510-4340-8d7c-e7430dfcd7e6/scratchpad/verify20_summary.txt) / 20"
```

```output
run 1 rc=0 ==================== 130 passed, 1796 deselected in 10.78s =====================
run 2 rc=0 ==================== 130 passed, 1796 deselected in 10.85s =====================
run 3 rc=0 ==================== 130 passed, 1796 deselected in 10.58s =====================
run 4 rc=0 ==================== 130 passed, 1796 deselected in 10.85s =====================
run 5 rc=0 ==================== 130 passed, 1796 deselected in 12.39s =====================
run 6 rc=0 ==================== 130 passed, 1796 deselected in 10.71s =====================
run 7 rc=0 ==================== 130 passed, 1796 deselected in 10.92s =====================
run 8 rc=0 ==================== 130 passed, 1796 deselected in 11.46s =====================
run 9 rc=0 ==================== 130 passed, 1796 deselected in 11.59s =====================
run 10 rc=0 ==================== 130 passed, 1796 deselected in 11.11s =====================
run 11 rc=0 ==================== 130 passed, 1796 deselected in 11.71s =====================
run 12 rc=0 ==================== 130 passed, 1796 deselected in 11.21s =====================
run 13 rc=0 ==================== 130 passed, 1796 deselected in 10.75s =====================
run 14 rc=0 ==================== 130 passed, 1796 deselected in 11.11s =====================
run 15 rc=0 ==================== 130 passed, 1796 deselected in 11.18s =====================
run 16 rc=0 ==================== 130 passed, 1796 deselected in 11.46s =====================
run 17 rc=0 ==================== 130 passed, 1796 deselected in 11.20s =====================
run 18 rc=0 ==================== 130 passed, 1796 deselected in 11.41s =====================
run 19 rc=0 ==================== 130 passed, 1796 deselected in 10.96s =====================
run 20 rc=0 ==================== 130 passed, 1796 deselected in 10.94s =====================
DONE
green runs: 20 / 20
```

For the record, the pre-fix root-causing loop also ran the selection 42 times with the original test and query and never reproduced the reported failure; the only two red runs in that loop were this branch's new order assertion executing against the old query during the RED step, which is the same failure shown above.

**Summary.** Neither order dependence nor an unstable sort could have failed the old test; its single recorded failure was environmental and its evidence was swallowed. The list query was nonetheless non-deterministic on `created_at` ties, and now orders by `created_at desc, id desc`. The test asserts every upload, proves paging under a forced tie, and passed 20/20 consecutive runs of the full selection. The same missing tiebreak in eight other services is filed as #530.
