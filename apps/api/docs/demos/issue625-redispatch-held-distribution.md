# #625 — approving a held episode distributes it

*2026-10-14T04:13:29Z by Showboat 0.6.1*
<!-- showboat-id: b28ec5a9-8816-4078-a85e-bdaec021e69e -->

The distribution stage alone, run eagerly against the real database with only the outbound webhook call stubbed: the released episode is published and ends 'complete'; a rejected publish ends 'distribution_failed'. The hold is remembered, inside the fail-closed screening write, only when the generation asked for distribution.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_held_distribution_redispatch.py --no-cov -p no:cacheprovider -q -v 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[[0-9]*%\]//; s/.*:://'
```

```output
test_the_released_episode_is_distributed_and_ends_complete PASSED [ 25%]
test_a_failed_redispatch_is_a_distribution_failure_not_a_failed_episode PASSED [ 50%]
test_a_held_distribution_is_remembered_only_when_one_was_requested[True-True] PASSED [ 75%]
test_a_held_distribution_is_remembered_only_when_one_was_requested[False-None] PASSED
```

Through the API: approval claims the episode as 'distributing' and dispatches for the project's active targets, with generation's RSS pre-flight; it dispatches nothing when no distribution was held, the feature is off, the feed cannot be made, or a newer run replaced the approved one; and no failure after the approval commit turns it into an error.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_episodes.py --no-cov -p no:cacheprovider -q -v -k 'redispatches or switched_off or broker_failure or planning_failure or newer_generation or rss_platform' 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[[0-9]*%\]//; s/.*:://'
```

```output
test_approving_redispatches_the_distribution_the_hold_skipped PASSED [ 12%]
test_approving_distributes_nothing_that_was_not_held_or_is_switched_off[False-True] PASSED [ 25%]
test_approving_distributes_nothing_that_was_not_held_or_is_switched_off[True-False] PASSED [ 37%]
test_a_broker_failure_still_approves_and_leaves_the_episode_complete PASSED [ 50%]
test_a_planning_failure_still_approves_and_leaves_the_episode_complete PASSED [ 62%]
test_a_newer_generation_is_never_claimed_by_an_older_approval PASSED [ 75%]
test_approval_generates_a_missing_feed_for_an_rss_platform PASSED [ 87%]
test_approval_skips_an_rss_platform_whose_feed_cannot_be_generated PASSED
```

Generation re-checks the status under a row lock before writing 'queued', so it cannot overwrite a claim made meanwhile:

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_generation_router.py --no-cov -p no:cacheprovider -q -v -k lost_the_episode 2>&1 | grep -E 'PASSED|FAILED' | sed 's/ *\[[0-9]*%\]//; s/.*:://'
```

```output
test_a_kickoff_that_lost_the_episode_meanwhile_is_a_conflict PASSED
```
