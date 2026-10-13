"""The finalize fallback during a real Redis outage (#635).

Each test runs in a subprocess whose broker and result backend point at a closed
port, because the Celery app reads them at import. Nothing is mocked: the
outage is real, and so are the database and local storage.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
DEAD_REDIS = "redis://127.0.0.1:1/0"


def _run_in_outage(code: str, timeout: int):
    env = {
        **os.environ,
        "CELERY_BROKER_URL": DEAD_REDIS,
        "CELERY_RESULT_BACKEND": DEAD_REDIS,
        "PYTHONPATH": str(API_ROOT),
        "LOG_LEVEL": "CRITICAL",
    }
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=API_ROOT, env=env,
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    return result, time.monotonic() - started


def test_delay_raises_promptly_when_redis_is_down():
    """Before #635 this blocked for 13+ minutes, so the fallback never ran."""
    result, elapsed = _run_in_outage(
        "from src.tasks.podcast_generation import finalize_episode_generation_task as t\n"
        "try:\n"
        "    t.delay(episode_id='x', generation_result={})\n"
        "    print('RETURNED')\n"
        "except Exception as exc:\n"
        "    print('RAISED', type(exc).__name__)\n",
        timeout=120,
    )

    assert "RAISED" in result.stdout, result.stdout + result.stderr
    assert elapsed < 30


def test_the_fallback_completes_the_episode_during_the_outage(tmp_path):
    """End to end: a finished generation is finalized in-process, on the real
    database, while Redis is unreachable."""
    result, elapsed = _run_in_outage(
        f"""
import uuid
from src.config import settings
from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.podcast_generation import _finalize_or_fall_back

settings.AWS_S3_BUCKET = None
settings.LOCAL_AUDIO_STORAGE_PATH = {str(tmp_path / 'audio')!r}
tenant = uuid.uuid4()
with SyncSessionLocal() as db:
    user = User(email=f"outage-{{uuid.uuid4()}}@test.local", password_hash="x", tenant_id=tenant)
    db.add(user); db.flush()
    project = Project(user_id=user.id, tenant_id=tenant, name="Outage")
    db.add(project); db.flush()
    episode = Episode(user_id=user.id, project_id=project.id, tenant_id=tenant, episode_number=1,
                      episode_metadata={{"title": "t"}}, generation_status="generating")
    db.add(episode); db.commit()
    user_id, episode_id = user.id, str(episode.id)
audio = {str(tmp_path / 'episode.mp3')!r}
open(audio, "wb").write(b"ID3" + bytes(64))
try:
    _finalize_or_fall_back(episode_id, {{
        "status": "success", "audio_file_path": audio, "transcript_path": None,
        "duration_seconds": 1.0, "file_size_bytes": 67, "error": None,
    }})
    with SyncSessionLocal() as db:
        print("STATUS", db.get(Episode, uuid.UUID(episode_id)).generation_status)
finally:
    with SyncSessionLocal() as db:
        db.delete(db.get(User, user_id)); db.commit()
""",
        timeout=180,
    )

    assert "STATUS complete" in result.stdout, result.stdout + result.stderr
    assert elapsed < 60
