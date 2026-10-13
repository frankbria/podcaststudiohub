# #635 — .delay() raises promptly in a Redis outage, so the finalize fallback runs

*2026-10-13T05:10:24Z by Showboat 0.6.1*
<!-- showboat-id: b272945a-71f9-4e33-b1ea-23303a91a249 -->

Before this change, with the broker and result backend pointed at a closed port, `finalize_episode_generation_task.delay(...)` had neither returned nor raised after **818 s**. The stack showed it waiting in `celery/backends/redis.py:on_task_call`: the result backend subscribes on every send, and that connection retries with no bound. Measured during #633.

Two changes, both needed (measured with each alone: `ignore_result` alone raised after 138 s; the connect timeout alone was still blocked at 272 s):
- finalize sets `ignore_result=True` (nothing reads its result), so a send no longer subscribes to the result backend;
- the broker transport gets `socket_connect_timeout: 5`.

The two tests below are the end-to-end proof. Each runs in a subprocess whose Celery broker and result backend point at a closed port, so the outage is real. The second finalizes a real episode on the real database through the real `_finalize_or_fall_back`.

```bash
. /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/testenv.sh && .venv/bin/python -m pytest tests/test_finalize_outage.py -v --no-cov -p no:cacheprovider --durations=2 2>&1 | grep -E "PASSED|FAILED|s call|passed|failed"
```

```output
tests/test_finalize_outage.py::test_delay_raises_promptly_when_redis_is_down PASSED [ 50%]
tests/test_finalize_outage.py::test_the_fallback_completes_the_episode_during_the_outage PASSED [100%]
11.36s call     tests/test_finalize_outage.py::test_the_fallback_completes_the_episode_during_the_outage
6.82s call     tests/test_finalize_outage.py::test_delay_raises_promptly_when_redis_is_down
============================== 2 passed in 18.60s ==============================
```

`.delay()` now raises in about 7 s, and the whole fallback (raise, then in-process finalize) completes the episode in about 11 s during the outage, against 818 s+ and never before.
