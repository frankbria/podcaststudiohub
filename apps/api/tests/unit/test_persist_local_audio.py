"""_persist_local_audio must never write outside LOCAL_AUDIO_STORAGE_PATH (issue #575).

The no-S3 fallback (#292) builds a real filesystem path from ``episode_id``.
``os.path.join`` honours ``..`` and lets an absolute component replace the
storage root, so a non-UUID id must be refused before anything is written.
"""
import os
from uuid import uuid4

import pytest

from src.config import settings
from src.tasks.podcast_generation import _persist_local_audio


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "storage" / "audio"
    monkeypatch.setattr(settings, "LOCAL_AUDIO_STORAGE_PATH", str(root))
    return root


@pytest.fixture
def generated(tmp_path):
    audio = tmp_path / "run" / "podcast.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"ID3 fake mp3")
    return audio


def _files_under(path):
    return sorted(
        os.path.join(dirpath, name)
        for dirpath, _, names in os.walk(path)
        for name in names
    )


@pytest.mark.parametrize("episode_id", [
    "../../escaped",
    "../audio-sibling",
    "/abs/escaped",
    "not-a-uuid",
    "",
])
def test_a_non_uuid_episode_id_is_rejected_before_anything_is_written(
    storage, generated, tmp_path, episode_id
):
    before = _files_under(tmp_path)

    with pytest.raises(ValueError, match="episode_id"):
        _persist_local_audio(str(generated), episode_id)

    # Nothing written anywhere, and the storage root was not even created.
    assert _files_under(tmp_path) == before
    assert not storage.exists()


def test_a_uuid_episode_id_is_persisted_inside_the_storage_root(storage, generated):
    episode_id = str(uuid4())

    dest = _persist_local_audio(str(generated), episode_id)

    assert dest == str(storage / f"episode-{episode_id}.mp3")
    assert (storage / f"episode-{episode_id}.mp3").read_bytes() == b"ID3 fake mp3"
