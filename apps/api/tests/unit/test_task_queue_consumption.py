"""Every task lands on a queue the worker consumes (#560).

The deployed worker runs `celery ... worker -B` with no `-Q`, so it consumes
exactly the queues the app declares. Before #560 none were declared, so it
consumed only the default `celery` queue while `task_routes` sent most tasks
to named queues: on the dev box 39,312 beat ticks of the reaper and the outbox
drain, and 11 content extractions, sat unconsumed in Redis. Two tasks also had
no route at all (their module globs never match a bare task name).
"""
from src.worker import celery_app


def _consumed():
    return {queue.name for queue in celery_app.conf.task_queues}


def _registered():
    return sorted(name for name in celery_app.tasks if not name.startswith("celery."))


def test_every_registered_task_routes_to_a_queue_the_worker_consumes():
    consumed = _consumed()
    stranded = {
        name: celery_app.amqp.router.route({}, name)["queue"].name
        for name in _registered()
    }
    stranded = {name: queue for name, queue in stranded.items() if queue not in consumed}

    assert not stranded, f"tasks routed to queues no worker consumes: {stranded}"


def test_the_default_queue_is_still_consumed():
    """Anything dispatched without a route (or by an older client) is not lost."""
    assert celery_app.conf.task_default_queue in _consumed()


def test_the_two_bare_named_tasks_reach_their_intended_queues():
    route = celery_app.amqp.router.route
    assert route({}, "merge_audio_snippets")["queue"].name == "audio_processing"
    assert route({}, "distribute_to_platform")["queue"].name == "distribution"
