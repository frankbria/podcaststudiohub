# #633 — the broker-outage finalize fallback uploads and completes

*2026-10-13T04:31:36Z by Showboat 0.6.1*
<!-- showboat-id: e87ca050-78d2-4211-aceb-17cc2cf6694e -->

When `.delay()` fails, `_finalize_or_fall_back` runs `finalize_episode_generation_task(...)` in-process. With a bucket configured, that call failed: no task id ("task_id must not be empty"), and in an outage no result backend either. This demo runs that exact call on the real database, a real S3 API (a throwaway SeaweedFS container), and the real upload task, with `CELERY_RESULT_BACKEND` pointed at a closed port. Nothing is mocked. Driver: `/tmp/demo_633.py`, env `/tmp/demo633env.sh`.

First, unmodified `main`, for contrast:

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && . /tmp/demo633env.sh && .venv/bin/python /tmp/demo_633.py 2>&1 | grep -v "^{" | grep -E "status|Error|must not" | head -5
```

```output
Finalization error for episode 0813c980-d66f-4c5c-9905-952eedfc3bde, attempt 1/4: task_id must not be empty. Got None instead.
    raise ValueError(f'task_id must not be empty. Got {task_id} instead.')
ValueError: task_id must not be empty. Got None instead.
```

Then this branch:

```bash
. /tmp/demo633env.sh && .venv/bin/python /tmp/demo_633.py 2>&1 | grep -v "^{"
```

```output
result backend=redis://127.0.0.1:1/0  (closed port)
finalize (synchronous, no task id): status=success
episode: generation_status=complete
  s3_key=podcasts/user-919db401-f1d7-47de-a561-af0d0c57e41b/episode-8a069215-b40a-4a77-98c1-de50099ea3e6.mp3
  in S3: 4099 bytes audio/mpeg
```

On `main` the call dies on its first progress write, before the upload. On this branch it skips that write, uploads to S3, and completes the episode, with the result backend unreachable throughout.

Not covered here: how `_finalize_or_fall_back` *reaches* this call. In a full Redis outage, `.delay()` does not fail fast. Celery's Redis result backend subscribes on every send (`on_task_call`), and that connection retries, so the fallback only runs once `.delay()` gives up. Measured and filed separately.
