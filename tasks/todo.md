# [P1.3] #520 — `except MaxRetriesExceededError` is dead code in 6 more tasks

Branch: `feature/issue-520-dead-maxretries-branches`. Plan source: issue body ("Done when" + "Suggested shape"), adapted below.

## Findings that shape the plan

- Celery `Task.retry(exc=e)` re-raises `e` on exhaustion; it never raises `MaxRetriesExceededError`. So today every
  one of the six sites already fails with the original exception — the change makes that explicit and rescues
  whatever was stranded in the dead branch.
- Stranded per site (what "was supposed to happen and never did"):
  - `content_extraction.py` ×2, `analytics.py`, `platform_distribution.py`: only a log line + an unread result dict.
    All four are fire-and-forget (`.delay()` / chain with `link_error`), nobody reads the dict. Terminal = log + `raise`.
  - `podcast_generation.py::generate_podcast_task`: the #294 `_update_episode(failed)` write AND
    `release_generation_lock` — so today an exhausted generation **leaks the Redis lock until TTL**. Terminal =
    log + failed write + release lock + `raise`. (`update_state(FAILURE)` dropped: raising is what sets FAILURE.)
  - `podcast_generation.py::finalize_episode_generation_task`: the #311 rollback + `generation_status="failed"`
    write. Finalize is dispatched via `.delay()` with **no link_error**, so today an exhausted finalize leaves the
    episode stuck in-progress forever. Terminal = log + rollback + failed write + `raise`.
- Distribution: `build_generation_workflow` attaches `link_error=on_workflow_failure` per distribution task, so
  `raise` is the designed exhausted-transient path (permanent errors still return `{status: failed}` for
  `on_distribution_complete`). Unchanged behaviour, now explicit.
- Tests: 13 mock sites across 9 files force the dead branch with `side_effect=MaxRetriesExceededError()`.
  `_make_celery_retry_exception` (test_task_retry.py) and `_make_celery_retry_exc` (test_platform_distribution_services.py,
  zero callers) both go. Scheduled-retry tests switch to `_scheduled_retry` + `pytest.raises(Retry)`; exhaustion
  tests become real-Celery tests (`push_request(retries=max_retries)`, no retry mock) per `TestRealRetryExhaustion`.

## Steps

1. **Simple sites (4)** — `content_extraction.py` (2 sites), `analytics.py`, `platform_distribution.py`:
   RED: real-exhaustion test per task in `test_content_extraction_task.py`, `test_url_reachability_task.py`,
   `test_analytics_track_task.py`, `test_platform_distribution_metadata.py`; convert existing mocked tests to
   `_scheduled_retry`. GREEN: `if self.request.retries >= self.max_retries: log; raise` before `self.retry`.
   Delete `_make_celery_retry_exc` from `test_platform_distribution_services.py`.
2. **podcast_generation sites (2)** — RED: real-exhaustion tests (generate: raises + failed write + lock released +
   run_dir removed; finalize: raises + rollback + failed status committed) in `test_podcast_generation_task.py`,
   `test_celery_workflow.py`, `test_task_retry.py`. GREEN: explicit terminal blocks. Delete
   `_make_celery_retry_exception`; convert the generation/finalize/distribution scheduled tests in `test_task_retry.py`.
3. Docstrings: drop "returns failed dict after retries" wording where the task now raises.

## Acceptance criteria

- [ ] Each of the six sites decides terminality with `if self.request.retries >= self.max_retries:`
- [ ] Stranded cleanup/status writes moved onto the path that runs (lock release, #294 write, #311 rollback+write)
- [ ] `_make_celery_retry_exception` deleted; no test mocks `retry` with `MaxRetriesExceededError`
- [ ] Every task has a terminal-behaviour test with no retry mock (real Celery decides)

## Autonomous decisions

- Terminal behaviour = `raise` (issue's suggested shape; preserves today's observed behaviour). Distribution's
  exhausted-transient path therefore still marks the whole episode `failed` via `on_workflow_failure`, whereas a
  permanent error yields `distribution_failed`. Pre-existing; noted in PR Known Limitations, not changed here.
