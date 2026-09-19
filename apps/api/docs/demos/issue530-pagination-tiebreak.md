# Issue #530: deterministic id tiebreak on every paginated list query

*2026-09-19T02:43:41Z*

Branch `feature/issue-530-pagination-tiebreak`. With LIMIT/OFFSET, Postgres returns rows whose sort keys tie in arbitrary order, so a client paging a list can see a row twice or never. #490 fixed this for audio snippets; this branch adds the primary key as the final sort key everywhere else. All runs below hit the real app stack and the local Postgres as the non-superuser `podcastfy_app` role, so RLS applies exactly as in production.

**Criteria 1 and 2: the SQL each list actually emits.** The block drops a throwaway pytest plugin that hooks SQLAlchemy's `before_cursor_execute` and prints the `ORDER BY` of every statement that sorts on `created_at`. It then runs the tie tests. Each test creates five rows through the API, forces them all to the same `created_at`, and pages through them two at a time.

```bash
P=$(mktemp -d) && cat > $P/sqlorder.py <<'EOF'
import re
from sqlalchemy import event
from sqlalchemy.engine import Engine
seen = set()
@event.listens_for(Engine, "before_cursor_execute")
def show(conn, cursor, statement, params, context, executemany):
    m = re.search(r"ORDER BY (.*?)(?:\s+LIMIT\b|\s*$)", statement, re.S)
    if m and "created_at" in m.group(1):
        line = " ".join(m.group(1).split())
        if line not in seen:
            seen.add(line)
            print("\n    ORDER BY " + line)
EOF
PYTHONPATH=$P uv run pytest tests/ -k created_at_tie -p sqlorder -p no:cacheprovider --no-cov -q -s 2>&1 | grep -E "ORDER BY|passed|failed"
```

```output
    ORDER BY content_sources.created_at ASC, content_sources.id ASC
    ORDER BY conversation_templates.created_at DESC, conversation_templates.id DESC
    ORDER BY distribution_targets.created_at DESC, distribution_targets.id DESC
    ORDER BY episode_layouts.created_at DESC, episode_layouts.id DESC
    ORDER BY episodes.created_at ASC, episodes.id ASC
    ORDER BY episodes.created_at DESC, episodes.id DESC
    ORDER BY projects.created_at DESC, projects.id DESC
    ORDER BY teams.created_at, teams.id
    ORDER BY tts_configurations.created_at DESC, tts_configurations.id DESC
[32m===================== [32m[1m11 passed[0m, [33m1946 deselected[0m[32m in 4.57s[0m[32m ======================[0m
```

Nine distinct clauses. Both distribution-target queries (the paged list and the generation-time active-target query) and the RSS completed-episode query emit a clause already printed above, so dedup folds them in. Episodes appear in both directions because the test is parametrized over `sort_order`. `episode_service` builds the tiebreak from the caller's choice rather than hard-coding `created_at`, so the same holds for `episode_number` (the default) and `duration_seconds`:

```bash
git diff main...HEAD -- src/services/episode_service.py | grep "^[-+]\s"
```

```output
+	# id breaks ties on any sort column so LIMIT/OFFSET pages stay stable (#530)
-		query = query.order_by(sort_column.desc())
+		query = query.order_by(sort_column.desc(), Episode.id.desc())
-		query = query.order_by(sort_column.asc())
+		query = query.order_by(sort_column.asc(), Episode.id.asc())
```

**Criterion 3: the tests prove the fix, not just run past it.** The next block removes only the service changes (tests stay as they are), runs the same 11 tests, and restores the fix. On the pre-fix code, every test fails on its ordering assertion. Each failure prints the ids in the order the pages actually returned them, so tied rows come back in arbitrary, insertion-like order rather than a defined one.

```bash
git diff main...HEAD -- src/services | git apply -R && trap "git diff main...HEAD -- src/services | git apply" EXIT; uv run pytest tests/ -k created_at_tie -p no:cacheprovider --no-cov -q 2>&1 | sed -E "s/\x1b\[[0-9;]*m//g" | grep -E "^FAILED|passed|failed" | sed -E "s/^FAILED tests\/([a-z_]+)\.py::[a-z_]+(\[[a-z]+\])? - (.{70}).*/FAILED \1\2 - \3…/"
```

```output
FAILED test_content - AssertionError: unstable paging under tied created_at: ['92a3d9a7-299e…
FAILED test_conversation_templates - AssertionError: unstable paging under tied created_at: ['4d987d7c-c307…
FAILED test_distribution_targets - AssertionError: unstable paging under tied created_at: ['11880e83-91ab…
FAILED test_distribution_wiring - AssertionError: assert ['714e6631-4b...8ad2ea0af633'] == ['e66eef36-7c…
FAILED test_episode_layouts - AssertionError: unstable paging under tied created_at: ['f5074af8-4bc8…
FAILED test_episodes[asc] - AssertionError: unstable paging under tied created_at: ['77d1c9dd-8a8c…
FAILED test_episodes[desc] - AssertionError: unstable paging under tied created_at: ['e7785588-5344…
FAILED test_projects - AssertionError: unstable paging under tied created_at: ['b38cf696-39db…
FAILED test_rss_feed - AssertionError: assert ['5a80b1e1-5e...9e3ca766056d'] == ['e5427a3f-cf…
FAILED test_teams - AssertionError: assert ['6184daea-2f...8c733e214148'] == ['2088f9c8-48…
FAILED test_tts_configurations - AssertionError: unstable paging under tied created_at: ['135e6c70-f368…
===================== 11 failed, 1946 deselected in 5.08s ======================
```

**Criterion 4: RSS order is stable across renders.** `test_rss_feed` marks five episodes complete, ties their `created_at`, and calls the feed's `_get_completed_episodes` twice. With the fix (first block: 11 passed), both renders return the identical `id desc` sequence. Without it (block above), the order fails that check.

The UUIDs in the failure lines are random per run, so `showboat verify` will show diffs in those ids. What should reproduce is the shape: 11 failed without the fix, 11 passed with it, and the same nine `ORDER BY` clauses.
