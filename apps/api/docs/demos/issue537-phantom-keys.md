# #537 — migration 019 clears the phantom snippet keys

*2026-10-13T22:22:47Z by Showboat 0.6.1*
<!-- showboat-id: 79bfd2de-8169-43bf-a10f-10ffcae22631 -->

The migration's real SQL runs on the real Postgres through alembic's `Operations`, inside a transaction rolled back after each test. The test seeds a phantom snippet (`s3_key` set, `s3_url` NULL) with a queued deletion, a real upload, and an unrelated queued deletion. Then the real alembic chain runs on the test database: up, down, up again.

```bash
. /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/testenv.sh && .venv/bin/python -m pytest tests/test_migration_019_null_phantom_snippet_keys.py -v --no-cov -p no:cacheprovider 2>&1 | grep -E "PASSED|FAILED|passed|failed"
```

```output
tests/test_migration_019_null_phantom_snippet_keys.py::test_chains_after_018 PASSED [ 33%]
tests/test_migration_019_null_phantom_snippet_keys.py::test_phantom_keys_are_nulled_and_their_queued_deletions_dropped PASSED [ 66%]
tests/test_migration_019_null_phantom_snippet_keys.py::test_a_rerun_changes_nothing PASSED [100%]
============================== 3 passed in 0.20s ===============================
```

```bash
. /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/testenv.sh && for c in "downgrade 018" "upgrade head" current; do .venv/bin/alembic $c 2>&1 | grep -E "Running|head|^0"; done
```

```output
INFO  [alembic.runtime.migration] Running downgrade 019 -> 018, Null the phantom audio_snippets.s3_key values written before #536
INFO  [alembic.runtime.migration] Running upgrade 018 -> 019, Null the phantom audio_snippets.s3_key values written before #536
019 (head)
```
