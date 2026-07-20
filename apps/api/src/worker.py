"""
Celery worker configuration for background tasks
"""
import uuid

from celery import Celery
from celery.signals import (
    before_task_publish,
    setup_logging as setup_logging_signal,
    task_postrun,
    task_prerun,
)
from datetime import timedelta

from src.config import settings
from src.logging_config import (
    CORRELATION_ID,
    TENANT_ID,
    init_sentry,
    setup_logging,
)

# Create Celery app
celery_app = Celery(
    "podcastfy",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=[
        "src.tasks.podcast_generation",
        "src.tasks.audio_composition",
        "src.tasks.s3_upload",
        "src.tasks.platform_distribution",
        "src.tasks.content_extraction",
        "src.tasks.callbacks",
        "src.tasks.maintenance",
        "src.tasks.analytics",
    ]
)

# Celery configuration
celery_app.conf.update(
    broker_url=settings.celery_broker,
    result_backend=settings.celery_backend,
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,  # For testing
    # Long-form generation needs a high ceiling. Invariant: soft < hard <
    # visibility_timeout so the in-task SoftTimeLimitExceeded handler fires (and
    # writes DB 'failed') before the hard kill, and the broker does not redeliver
    # an in-flight message as a duplicate before it finishes/is killed (issue #294).
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    broker_transport_options={
        "visibility_timeout": settings.CELERY_BROKER_VISIBILITY_TIMEOUT,
    },
    worker_prefetch_multiplier=1,  # Take one task at a time
    worker_max_tasks_per_child=50,  # Restart workers after 50 tasks
    task_acks_late=True,  # Acknowledge tasks after completion
    task_reject_on_worker_lost=True,  # Requeue tasks if worker crashes
)

# Task routes (optional - for future scaling)
celery_app.conf.task_routes = {
    "generate_podcast": {"queue": "podcast_generation"},
    "finalize_episode_generation": {"queue": "podcast_generation"},
    "src.tasks.podcast_generation.*": {"queue": "podcast_generation"},
    "src.tasks.audio_composition.*": {"queue": "audio_processing"},
    "upload_to_s3": {"queue": "uploads"},
    "src.tasks.s3_upload.*": {"queue": "uploads"},
    "src.tasks.platform_distribution.*": {"queue": "distribution"},
    "extract_content": {"queue": "content_extraction"},
    "validate_url_reachability": {"queue": "content_extraction"},
    "src.tasks.content_extraction.*": {"queue": "content_extraction"},
    "src.tasks.callbacks.*": {"queue": "callbacks"},
    "on_upload_complete": {"queue": "callbacks"},
    "on_composition_complete": {"queue": "callbacks"},
    "on_distribution_complete": {"queue": "callbacks"},
    "on_workflow_complete": {"queue": "callbacks"},
    "on_workflow_failure": {"queue": "callbacks"},
    "reap_stuck_episodes": {"queue": "callbacks"},
    "drain_storage_deletion_outbox": {"queue": "callbacks"},
    "track_analytics_event": {"queue": "callbacks"},
    "src.tasks.analytics.*": {"queue": "callbacks"},
}

# Beat schedule — periodic reaper that fails episodes stuck in a non-terminal
# status past EPISODE_REAP_THRESHOLD_SECONDS, a final safety net for runs that
# slip past every in-task guard (worker crash, broker loss) (issue #294).
celery_app.conf.beat_schedule = {
    "reap-stuck-episodes": {
        "task": "reap_stuck_episodes",
        "schedule": timedelta(seconds=settings.REAP_STUCK_EPISODES_INTERVAL_SECONDS),
    },
    # Durable backstop for the storage-deletion outbox (issue #366): delete
    # flows also trigger a prompt drain post-commit, but that trigger is
    # best-effort (broker down must never fail the request), so this periodic
    # tick is what guarantees a queued deletion is retried until it succeeds.
    "drain-storage-deletion-outbox": {
        "task": "drain_storage_deletion_outbox",
        "schedule": timedelta(seconds=settings.STORAGE_GC_INTERVAL_SECONDS),
    },
}

# ── Observability: structured logs + correlation across the API→chain hop (#320)
#
# Propagation rides on message HEADERS, not task kwargs. Kwargs would mean
# touching every dispatch site and adding a parameter to every task signature —
# and the generation chain uses immutable .si() signatures precisely so that
# nothing extra is threaded positionally (issue #211). Headers are invisible to
# task code and survive chains, links and retries untouched.

# Header names. Celery reserves the plain `id` header, hence the prefix.
CORRELATION_ID_HEADER = "x_request_id"
TENANT_ID_HEADER = "x_tenant_id"


@setup_logging_signal.connect
def _configure_worker_logging(**_kwargs):
    """Use our formatter in the worker instead of Celery's default.

    Connecting to this signal at all disables Celery's own logging config, which
    is what lets the worker and uvicorn share one JSON format (issue #320, AC5).
    """
    setup_logging()
    init_sentry()


@before_task_publish.connect
def _propagate_context_to_task(headers=None, **_kwargs):
    """Stamp the publisher's request/tenant ids onto the outgoing message.

    Fires in whichever process publishes: the API (so a task inherits the HTTP
    request's id) and the worker (so a chained/retried task inherits its
    parent's), which is what stitches a whole generation run to one id.
    """
    if headers is None:
        return
    # A task published outside any request context (beat: reap_stuck_episodes,
    # drain_storage_deletion_outbox) has no id to inherit, so mint one — every
    # run stays traceable, and its logs group.
    headers[CORRELATION_ID_HEADER] = CORRELATION_ID.get() or str(uuid.uuid4())
    tenant_id = TENANT_ID.get()
    if tenant_id:
        headers[TENANT_ID_HEADER] = tenant_id


@task_prerun.connect
def _bind_task_context(task=None, **_kwargs):
    """Bind the message's ids into the worker's context for the task's lifetime."""
    request = getattr(task, "request", None)
    correlation_id = getattr(request, CORRELATION_ID_HEADER, None) or str(uuid.uuid4())
    CORRELATION_ID.set(correlation_id)
    TENANT_ID.set(getattr(request, TENANT_ID_HEADER, None))


@task_postrun.connect
def _unbind_task_context(**_kwargs):
    """Clear the ids so a pooled worker can't leak them into the next task."""
    CORRELATION_ID.set(None)
    TENANT_ID.set(None)


if __name__ == "__main__":
    celery_app.start()
