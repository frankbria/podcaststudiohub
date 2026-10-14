# #625 — approving a held episode distributes it

*2026-10-14T03:40:31Z by Showboat 0.6.1*
<!-- showboat-id: a0085a1e-8e6b-44f2-ba85-3c1f5d2c6469 -->

The distribution stage alone, run eagerly against the real database with only the outbound webhook call stubbed: the released episode is published and ends 'complete'; a rejected publish ends 'distribution_failed' (audio stays usable). The third test shows the hold is remembered only when the generation had asked for distribution.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_held_distribution_redispatch.py --no-cov -p no:cacheprovider -q -v 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[.*//'
```

```output
tests/test_held_distribution_redispatch.py::test_the_released_episode_is_distributed_and_ends_complete PASSED
tests/test_held_distribution_redispatch.py::test_a_failed_redispatch_is_a_distribution_failure_not_a_failed_episode PASSED
tests/test_held_distribution_redispatch.py::test_a_held_distribution_is_remembered_only_when_one_was_requested
tests/test_held_distribution_redispatch.py::test_a_held_distribution_is_remembered_only_when_one_was_requested
```

Through the API: approval dispatches that workflow for the project's active webhook target, and dispatches nothing when no distribution was held or the feature is switched off.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_episodes.py --no-cov -p no:cacheprovider -q -v -k 'redispatches or switched_off' 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[.*//; s/.*:://'
```

```output
test_approving_redispatches_the_distribution_the_hold_skipped PASSED
test_approving_distributes_nothing_that_was_not_held_or_is_switched_off
test_approving_distributes_nothing_that_was_not_held_or_is_switched_off
```
