"""StorageDeletionOutbox routes an S3 transcript key to s3_key (issue #543).

``episodes.transcript_path`` holds either an S3 key (bucket configured) or a
local path (the no-S3 fallback, #292), and both delete flows queue it as
``file_path``. The outbox model is the one constructor every delete flow goes
through, so that is where the value is routed to the column the drain deletes.
"""
from uuid import uuid4

import pytest

from src.engine.transcript import build_transcript_s3_key
from src.models.storage_deletion_outbox import StorageDeletionOutbox


def test_an_s3_transcript_key_queued_as_a_file_path_becomes_an_s3_deletion():
    key = build_transcript_s3_key(str(uuid4()), str(uuid4()))

    row = StorageDeletionOutbox(tenant_id=uuid4(), file_path=key)

    assert (row.s3_key, row.file_path) == (key, None)


def test_a_local_transcript_path_stays_a_file_deletion():
    path = f"storage/audio/episode-{uuid4()}.transcript.json"

    row = StorageDeletionOutbox(tenant_id=uuid4(), file_path=path)

    assert (row.s3_key, row.file_path) == (None, path)


def test_a_local_audio_path_is_untouched():
    path = f"storage/audio/episode-{uuid4()}.mp3"

    row = StorageDeletionOutbox(tenant_id=uuid4(), file_path=path)

    assert row.file_path == path and row.s3_key is None


def test_an_uppercase_uuid_transcript_key_is_routed_too():
    key = build_transcript_s3_key(str(uuid4()), str(uuid4())).upper().replace(
        "PODCASTS/USER-", "podcasts/user-"
    ).replace("/EPISODE-", "/episode-").replace(".TRANSCRIPT.JSON", ".transcript.json")

    row = StorageDeletionOutbox(tenant_id=uuid4(), file_path=key)

    assert row.s3_key == key


@pytest.mark.parametrize("kwargs_order", ["s3_key_first", "file_path_first"])
def test_a_second_object_in_one_row_is_refused_not_silently_dropped(kwargs_order):
    audio = f"podcasts/user-{uuid4()}/episode-{uuid4()}.mp3"
    transcript = build_transcript_s3_key(str(uuid4()), str(uuid4()))
    kwargs = (
        {"s3_key": audio, "file_path": transcript}
        if kwargs_order == "s3_key_first"
        else {"file_path": transcript, "s3_key": audio}
    )

    with pytest.raises(ValueError):
        StorageDeletionOutbox(tenant_id=uuid4(), **kwargs)
