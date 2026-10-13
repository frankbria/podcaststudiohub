"""upload_to_s3_task stamps held episode audio (#626), against the real DB.

Only boto3 is faked (the external S3 boundary); the hold state is read from a
committed episode row, as the worker does.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.database import SyncSessionLocal
from src.models.episode import Episode
from src.models.project import Project
from src.models.user import User
from src.tasks.podcast_generation import build_podcast_s3_key
from src.tasks.s3_upload import upload_to_s3_task


@pytest.fixture
def episode_with_review():
    created = []

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
