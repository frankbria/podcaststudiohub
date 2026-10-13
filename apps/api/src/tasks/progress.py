"""Best-effort progress reporting for tasks that also run synchronously (#633).

``finalize_episode_generation_task`` is the safety net for a broker outage:
``_finalize_or_fall_back`` runs it in-process when ``.delay()`` fails, so the
paid audio still reaches storage. Its progress writes broke that net twice
over: a direct call has no request id, and Celery's ``update_state`` raises
"task_id must not be empty"; and the broker and the result backend are the
same Redis in every shipped config, so in the very outage the fallback exists
for, the write fails with a connection error even with an id.

Progress is what a UI polls, not part of the work. A task using this base
reports it when it can and never fails because it could not.
"""
import logging

from celery import Task
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class BestEffortProgressTask(Task):
    """A task whose ``update_state`` never fails the task."""

    def update_state(self, task_id=None, state=None, meta=None, **kwargs):
        task_id = task_id or self.request.id
        if task_id is None:
            # Called synchronously: there is no task state to report to.
            return
        try:
            super().update_state(task_id=task_id, state=state, meta=meta, **kwargs)
        except (RedisError, OSError) as exc:
            logger.warning("Task %s: progress not reported (result backend unreachable): %s", task_id, exc)
