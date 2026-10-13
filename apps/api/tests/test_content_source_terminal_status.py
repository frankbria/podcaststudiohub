"""A content source whose task exhausts its retries is marked failed (#527).

Errors the extraction service does not classify (session or event-loop level,
e.g. a DB blip) retry three times and then fail the task. Before #527 nothing
on that path touched the row, so it kept its last status and the polling UI
showed a dead source as still in progress.

Real database rows, real Celery retry decision (no retry mock): only the
unclassified error itself is injected.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.database import SyncSessionLocal
from src.models.content_source import ContentSource
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.content_extraction import extract_content_task, validate_url_reachability_task


@pytest.fixture
def content_source():
    tenant = uuid.uuid4()
    with SyncSessionLocal() as db:
        user = User(email=f"src527-{uuid.uuid4()}@test.local", password_hash="x", tenant_id=tenant)
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, tenant_id=tenant, name="P")
        db.add(project)
        db.flush()
        episode = Episode(user_id=user.id, project_id=project.id, tenant_id=tenant,
                          episode_number=1, episode_metadata={"title": "E"})
        db.add(episode)
        db.flush()
        source = ContentSource(episode_id=episode.id, tenant_id=tenant, source_type="url",
                               source_data={"url": "https://example.com/post"},
                               extraction_status="extracting")
        db.add(source)
        db.commit()
        user_id, source_id = user.id, str(source.id)
    yield source_id
    with SyncSessionLocal() as db:
        db.delete(db.get(User, user_id))
        db.commit()


def _exhaust(task, **kwargs):
    """Run with retries at the limit and Celery's real retry decision.

    The async helpers are replaced too: with only asyncio.run raising, the
    coroutine handed to it is never awaited, and that RuntimeWarning surfaces
    (as an error) in whichever test happens to run next.
    """
    task.push_request(retries=task.max_retries, called_directly=False, id=f"exhaust-{uuid.uuid4()}")
    try:
        with patch("src.tasks.content_extraction._extract_content_async", MagicMock()), \
             patch("src.tasks.content_extraction._validate_url_reachability_async", MagicMock()), \
             patch("src.tasks.content_extraction.asyncio.run", side_effect=ConnectionError("db went away")):
            with pytest.raises(ConnectionError, match="db went away"):
                task.run(**kwargs)
    finally:
        task.pop_request()


def _row(source_id):
    with SyncSessionLocal() as db:
        source = db.get(ContentSource, uuid.UUID(source_id))
        return source.extraction_status, source.error_message


@pytest.mark.parametrize(
    ("task", "extra"),
    [(extract_content_task, {"source_type": "url"}), (validate_url_reachability_task, {})],
)
def test_exhausted_retries_mark_the_source_failed_and_still_fail_the_task(content_source, task, extra):
    _exhaust(task, content_source_id=content_source, **extra)

    status, message = _row(content_source)
    assert status == "failed"
    assert "db went away" in message


def test_a_failed_status_write_never_hides_the_original_error(content_source):
    """The terminal path is often a DB outage, so the write may fail too; the
    task must still fail with the original exception."""
    with patch("src.tasks.content_extraction.SyncSessionLocal", side_effect=OSError("db down")):
        _exhaust(extract_content_task, content_source_id=content_source, source_type="url")

    assert _row(content_source)[0] == "extracting"
