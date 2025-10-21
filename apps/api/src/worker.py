"""
Celery worker configuration for background tasks
"""
from celery import Celery

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
    ]
)

# Celery configuration
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,  # For testing
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,  # Take one task at a time
    worker_max_tasks_per_child=50,  # Restart workers after 50 tasks
    task_acks_late=True,  # Acknowledge tasks after completion
    task_reject_on_worker_lost=True,  # Requeue tasks if worker crashes
)

# Task routes (optional - for future scaling)
celery_app.conf.task_routes = {
    "src.tasks.podcast_generation.*": {"queue": "podcast_generation"},
    "src.tasks.audio_composition.*": {"queue": "audio_processing"},
    "src.tasks.s3_upload.*": {"queue": "uploads"},
    "src.tasks.platform_distribution.*": {"queue": "distribution"},
}

# Beat schedule (optional - for periodic tasks)
celery_app.conf.beat_schedule = {
    # Example: Clean up old temporary files every day
    # "cleanup-temp-files": {
    #     "task": "src.tasks.maintenance.cleanup_temp_files",
    #     "schedule": crontab(hour=2, minute=0),  # 2 AM daily
    # },
}

if __name__ == "__main__":
    celery_app.start()
