# Issue #520: retry exhaustion decided explicitly in the six remaining Celery tasks

*2026-09-16T03:30:20Z*

Celery 5.6 `Task.retry(exc=e)` re-raises the original exception when the retry budget is spent; it never raises `MaxRetriesExceededError`. Six tasks caught that exception anyway, so the cleanup and status writes inside those branches never ran. Each acceptance criterion from the issue is exercised below against the real Celery task objects, a real Redis, and (for the before/after) a worktree of `main`.

**Criterion 1 — every site decides terminality with `self.request.retries >= self.max_retries`.** No `except self.MaxRetriesExceededError:` handler remains under `src/tasks`; the explicit check appears at the six sites from the issue plus the three fixed by #498.

```bash
grep -rn "except self.MaxRetriesExceededError:" src/tasks/ || echo "no except-MaxRetriesExceededError handler left in src/tasks"; echo; grep -rc "self.request.retries >= self.max_retries" src/tasks/*.py | grep -v ":0$"
```

```output
no except-MaxRetriesExceededError handler left in src/tasks

src/tasks/analytics.py:1
src/tasks/audio_composition.py:1
src/tasks/content_extraction.py:2
src/tasks/platform_distribution.py:1
src/tasks/podcast_generation.py:2
src/tasks/s3_upload.py:2
```

**Criterion 3 — the dead-branch test helpers are gone and no test mocks `retry` with `MaxRetriesExceededError`.**

```bash
grep -rn "_make_celery_retry_exception\|_make_celery_retry_exc\|side_effect=.*MaxRetriesExceededError" tests/ || echo "no test forces the dead branch any more"
```

```output
no test forces the dead branch any more
```

**Criterion 2 — what was stranded now runs.** The probe below exhausts `generate_podcast_task` (podcastfy mocked to raise, retries at the limit, no `retry` mock so real Celery decides) with the REAL per-episode Redis lock. First against a worktree of `main`: the task raises, but the lock key survives (leaked until TTL) and no `failed` status is written.

```bash
cd /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/main-wt/apps/api && PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/probe_lock.py 2>&1 | grep -v '^{"timestamp'
```

```output
Podcast generation error for episode 00000000-0000-0000-0000-000000000520, attempt 4/4: LLM provider down
attempt        : 4 of 4
outcome        : RAISED RuntimeError: LLM provider down
release called : False (key existed before release: None)
lock key now   : 1 (0 = released, 1 = LEAKED until TTL)
last DB write  : None | None
```

Same probe against this branch: the `failed` status write (#294) and the lock release both run before the original exception propagates, so the Redis key is gone.

```bash
PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/probe_lock.py 2>&1 | grep -v '^{"timestamp'
```

```output
Podcast generation error for episode 00000000-0000-0000-0000-000000000520, attempt 4/4: LLM provider down
Podcast generation failed after 3 retries for episode 00000000-0000-0000-0000-000000000520: LLM provider down
attempt        : 4 of 4
outcome        : RAISED RuntimeError: LLM provider down
release called : True (key existed before release: 1)
lock key now   : 0 (0 = released, 1 = LEAKED until TTL)
last DB write  : {'generation_status': 'failed'} | failed
```

`finalize_episode_generation_task` is dispatched with no `link_error`, so on `main` an exhausted finalize left the episode in-progress forever: the session sees only the failing `get`, the row still says `generating`.

```bash
cd /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/main-wt/apps/api && PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/probe_finalize.py 2>&1 | grep -v '^{"timestamp'
```

```output
Finalization error for episode 00000000-0000-0000-0000-000000000521, attempt 4/4: Database connection lost
outcome            : RAISED RuntimeError: Database connection lost
session calls      : ['get']
episode status now : generating | finalizing
```

On this branch the #311 rollback and the `failed` write are committed before the error propagates.

```bash
PYTHONPATH=. /home/frankbria/projects/podcaststudiohub/apps/api/.venv/bin/python /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/probe_finalize.py 2>&1 | grep -v '^{"timestamp'
```

```output
Finalization error for episode 00000000-0000-0000-0000-000000000521, attempt 4/4: Database connection lost
Finalization failed after 3 retries for episode 00000000-0000-0000-0000-000000000521: Database connection lost
outcome            : RAISED RuntimeError: Database connection lost
session calls      : ['get', 'rollback', 'get', 'commit']
episode status now : failed | failed
```

**Criterion 4 — a terminal-behaviour test per task with no retry mock.** Each of the six tasks (plus the two from #498) has a test that pushes a request with `retries=max_retries` and lets real Celery decide.

```bash
uv run pytest tests/ -p no:cacheprovider --no-cov -o addopts="" -q -k "exhausted_retries or exhaustion or does_not_publish_without_uploaded_audio or cleanup_rolls_back or cleanup_degrades or cleanup_proceeds or terminal_failure_cleans_up_run_dir or after_max_retries or workflow_chain_not_called" -rA 2>&1 | grep -E "^PASSED|^FAILED|^[0-9]+ (passed|failed)"
```

```output
PASSED tests/test_celery_workflow.py::TestErrorHandling::test_workflow_chain_not_called_on_generation_failure
PASSED tests/test_celery_workflow.py::TestFailurePathsWriteDbStatus::test_retry_exhaustion_writes_failed
PASSED tests/test_s3_upload.py::TestNonRetryableS3Errors::test_retryable_client_error_raises_after_max_retries
PASSED tests/test_script_generation.py::test_call_gemini_api_exhausted_retries_raises
PASSED tests/unit/test_analytics_track_task.py::test_exhausted_retries_propagate_the_original_exception
PASSED tests/unit/test_audio_composition_task.py::TestRealRetryExhaustion::test_exhausted_retries_propagate_the_original_exception
PASSED tests/unit/test_content_extraction_task.py::test_exhausted_retries_propagate_the_original_exception
PASSED tests/unit/test_platform_distribution_metadata.py::TestDistributeTaskPopulatesMetadata::test_task_does_not_publish_without_uploaded_audio
PASSED tests/unit/test_podcast_generation_task.py::test_exhausted_retries_propagate_the_original_exception
PASSED tests/unit/test_podcast_generation_task.py::test_terminal_failure_cleans_up_run_dir
PASSED tests/unit/test_task_retry.py::TestGeneratePodcastTaskRetry::test_exhausted_retries_fail_the_task_and_release_the_lock
PASSED tests/unit/test_task_retry.py::TestFinalizeEpisodeGenerationTaskRetry::test_cleanup_rolls_back_failed_transaction_before_marking_failed
PASSED tests/unit/test_task_retry.py::TestFinalizeEpisodeGenerationTaskRetry::test_cleanup_degrades_gracefully_when_cleanup_commit_fails
PASSED tests/unit/test_task_retry.py::TestFinalizeEpisodeGenerationTaskRetry::test_cleanup_proceeds_when_rollback_itself_fails
PASSED tests/unit/test_url_reachability_task.py::test_exhausted_retries_propagate_the_original_exception
15 passed, 1911 deselected in 1.72s
```

The probe scripts used above are reproduced here so the document stands on its own.

```bash
cat /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/probe_lock.py
```

```output
"""Exhaust generate_podcast_task's retries with REAL Celery deciding and a REAL
Redis lock; report whether the lock survives the terminal path and what status
was written. Run from apps/api (of whichever tree is under test)."""
import sys
import types
from unittest.mock import MagicMock, patch

from redis import Redis

from src.config import settings
from src.tasks import podcast_generation as pg
from src.tasks.idempotency import _lock_key

EPISODE = "00000000-0000-0000-0000-000000000520"
task = pg.generate_podcast_task
r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
key = _lock_key(EPISODE)
r.delete(key)

client = MagicMock()
client.generate_podcast = MagicMock(side_effect=RuntimeError("LLM provider down"))
podcastfy = types.ModuleType("podcastfy")
podcastfy.client = client

seen = {}
real_release = pg.release_generation_lock


def spy_release(episode_id, task_id):
    seen["lock_before_release"] = r.exists(key)
    real_release(episode_id, task_id)


task.push_request(retries=task.max_retries, called_directly=False, id="demo-520")
try:
    with patch.dict(sys.modules, {"podcastfy": podcastfy, "podcastfy.client": client}), \
         patch.object(task, "update_state"), \
         patch("src.tasks.podcast_generation._load_generation_status", return_value=None), \
         patch("src.tasks.podcast_generation.release_generation_lock", side_effect=spy_release), \
         patch("src.tasks.podcast_generation._update_episode") as upd:
        try:
            task.run(episode_id=EPISODE, urls=["https://example.com"])
            outcome = "RETURNED (no exception)"
        except Exception as exc:  # noqa: BLE001
            outcome = f"RAISED {type(exc).__name__}: {exc}"
finally:
    task.pop_request()

last = upd.call_args.kwargs if upd.call_args else {}
print("attempt        :", task.max_retries + 1, "of", task.max_retries + 1)
print("outcome        :", outcome)
print("release called :", "lock_before_release" in seen, f"(key existed before release: {seen.get('lock_before_release')})")
print("lock key now   :", r.exists(key), "(0 = released, 1 = LEAKED until TTL)")
print("last DB write  :", last.get("updates"), "|", (last.get("progress_updates") or {}).get("status"))
r.delete(key)
```

```bash
cat /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/211ff5c3-aaac-4cd9-9010-8c30118aa8f8/scratchpad/probe_finalize.py
```

```output
"""Exhaust finalize_episode_generation_task's retries with REAL Celery deciding
against a session whose first get() fails; report whether the #311 rollback and
'failed' status write happen before the original error propagates."""
from unittest.mock import MagicMock, patch

from src.tasks import podcast_generation as pg

task = pg.finalize_episode_generation_task
episode = MagicMock()
episode.generation_status = "generating"
episode.generation_progress = {"stage": "finalizing"}

db = MagicMock()
db.get.side_effect = [RuntimeError("Database connection lost"), episode]
db.__enter__ = MagicMock(return_value=db)
db.__exit__ = MagicMock(return_value=False)

task.push_request(retries=task.max_retries, called_directly=False, id="demo-520-fin")
try:
    with patch("src.tasks.podcast_generation.SyncSessionLocal", return_value=db), \
         patch("src.tasks.podcast_generation.settings") as s, \
         patch.object(task, "update_state"):
        s.AWS_S3_BUCKET = None
        try:
            task.run(
                episode_id="00000000-0000-0000-0000-000000000521",
                generation_result={"status": "success", "audio_file_path": "/tmp/x.mp3",
                                   "duration_seconds": 1.0, "file_size_bytes": 1},
            )
            outcome = "RETURNED (no exception)"
        except Exception as exc:  # noqa: BLE001
            outcome = f"RAISED {type(exc).__name__}: {exc}"
finally:
    task.pop_request()

calls = [n for n, _, _ in db.mock_calls]
print("outcome            :", outcome)
print("session calls      :", [c for c in calls if c in ("get", "rollback", "commit")])
print("episode status now :", episode.generation_status, "|", episode.generation_progress.get("stage"))
```
