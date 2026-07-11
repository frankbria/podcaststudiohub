"""
Celery worker configuration for background tasks
"""
from celery import Celery
from datetime import timedelta

from src.config import settings

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
    "src.tasks.content_extraction.*": {"queue": "content_extraction"},
    "src.tasks.callbacks.*": {"queue": "callbacks"},
    "on_upload_complete": {"queue": "callbacks"},
    "on_composition_complete": {"queue": "callbacks"},
    "on_distribution_complete": {"queue": "callbacks"},
    "on_workflow_complete": {"queue": "callbacks"},
    "on_workflow_failure": {"queue": "callbacks"},
    "reap_stuck_episodes": {"queue": "callbacks"},
    "drain_storage_deletion_outbox": {"queue": "callbacks"},
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

if __name__ == "__main__":
    celery_app.start()
