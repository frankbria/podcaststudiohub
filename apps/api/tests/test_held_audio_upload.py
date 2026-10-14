"""upload_to_s3_task stamps held episode audio (#626), against the real DB.

Only boto3 is faked (the external S3 boundary); the hold state is read from a
committed episode row, as the worker does.
"""
import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.podcast_generation import build_podcast_s3_key
from src.tasks.content_review import episode_held_for_review
from src.tasks.s3_upload import upload_to_s3_task


episode_ids: list = []  # the episodes the current test's fixture made


def _set_review(episode_id, review, commit=True):
    """Approval's write: FOR UPDATE, then the new review state. Returns the open
    session when not committing, so a test can hold the lock."""
    db = SyncSessionLocal()
    episode = db.get(Episode, episode_id, with_for_update=True)
    episode.generation_progress = {**episode.generation_progress, "content_review": review}
    if commit:
        db.commit()
        db.close()
    return db


@pytest.fixture
def episode_with_review():
    created = []
    episode_ids.clear()

    def make(review):
        tenant = uuid.uuid4()
        with SyncSessionLocal() as db:
            user = User(email=f"held-audio-{uuid.uuid4()}@test.local", password_hash="x", tenant_id=tenant)
            db.add(user)
            db.flush()
            project = Project(user_id=user.id, tenant_id=tenant, name="P")
            db.add(project)
            db.flush()
            episode = Episode(
                user_id=user.id, project_id=project.id, tenant_id=tenant, episode_number=1,
                episode_metadata={"title": "E"}, generation_status="uploading",
                generation_progress={"content_review": review},
            )
            db.add(episode)
            db.commit()
            created.append(user.id)
            episode_ids.append(episode.id)
            return build_podcast_s3_key(str(user.id), str(episode.id))

    yield make
    with SyncSessionLocal() as db:
        for user_id in created:
            db.delete(db.get(User, user_id))
        db.commit()


def _upload(tmp_path, s3_key):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3")
    client = MagicMock()
    with patch("src.tasks.s3_upload.boto3.client", return_value=client), patch.object(
        upload_to_s3_task, "update_state"
    ):
        upload_to_s3_task.run(file_path=str(audio), s3_key=s3_key, bucket_name="bucket")
    return client.upload_file.call_args.kwargs["ExtraArgs"]


def test_held_episode_audio_is_stamped_pending(tmp_path, episode_with_review):
    extra = _upload(tmp_path, episode_with_review("pending"))

    assert extra["Metadata"] == {"content-review": "pending"}
    assert extra["ContentType"] == "audio/mpeg"


@pytest.mark.parametrize("review", [None, "approved"])
def test_unheld_episode_audio_carries_no_mark(tmp_path, episode_with_review, review):
    extra = _upload(tmp_path, episode_with_review(review))

    assert "Metadata" not in extra


def test_a_non_episode_key_is_never_looked_up(tmp_path):
    with patch("src.tasks.content_review.SyncSessionLocal") as session:
        extra = _upload(tmp_path, "audio-snippets/user-x/intro.mp3")

    session.assert_not_called()
    assert "Metadata" not in extra


# --- #629: a redelivered upload racing approval must not leave the mark ---

def _extras(client):
    return [call.kwargs["ExtraArgs"] for call in client.upload_file.call_args_list]


def test_an_approval_between_the_hold_read_and_the_object_write_leaves_no_mark(tmp_path, episode_with_review):
    s3_key = episode_with_review("pending")

    client = MagicMock()
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3")
    writes = []

    def upload_file(*args, **kwargs):
        writes.append(kwargs["ExtraArgs"])
        if len(writes) == 1:
            _set_review(episode_ids[0], "approved")

    client.upload_file.side_effect = upload_file
    with patch("src.tasks.s3_upload.boto3.client", return_value=client), patch.object(
        upload_to_s3_task, "update_state"
    ):
        upload_to_s3_task.run(file_path=str(audio), s3_key=s3_key, bucket_name="bucket")

    assert writes[0]["Metadata"] == {"content-review": "pending"}
    assert len(writes) == 2, "the marked object must be replaced"
    assert "Metadata" not in writes[1]
    assert writes[1]["ContentType"] == "audio/mpeg"


def test_a_still_held_episode_is_written_once_and_stays_marked(tmp_path, episode_with_review):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3")
    client = MagicMock()
    with patch("src.tasks.s3_upload.boto3.client", return_value=client), patch.object(
        upload_to_s3_task, "update_state"
    ):
        upload_to_s3_task.run(file_path=str(audio), s3_key=episode_with_review("pending"), bucket_name="bucket")

    assert _extras(client) == [{"ContentType": "audio/mpeg", "Metadata": {"content-review": "pending"}}]


def test_the_recheck_waits_for_an_approval_that_has_not_committed_yet(episode_with_review):
    """A plain re-read would see 'pending' between approval's clear and its
    commit; FOR SHARE blocks behind approval's FOR UPDATE instead."""
    episode_with_review("pending")
    episode_id = str(episode_ids[0])
    approval = _set_review(episode_ids[0], "approved", commit=False)  # lock held, uncommitted
    answer = []
    recheck = threading.Thread(
        target=lambda: answer.append(episode_held_for_review(episode_id, after_approval=True))
    )
    try:
        recheck.start()
        recheck.join(timeout=0.5)
        assert recheck.is_alive(), "the re-check must block while approval holds the row"
        assert episode_held_for_review(episode_id) is True  # the unlocked read still says pending
    finally:
        approval.commit()
        approval.close()
        recheck.join(timeout=5)

    assert answer == [False]
