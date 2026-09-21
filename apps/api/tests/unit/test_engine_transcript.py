"""Unit tests for engine transcript persistence (issue #541).

``episodes.transcript_path`` has been ``NULL`` for every episode ever generated
(issue #309): podcastfy wrote the transcript into the per-run temp dir, which
``_cleanup_temp_file`` deleted with the audio. These tests cover the helper that
gives the engine's ``Script`` a durable home so #543 can populate that column.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import settings
from src.engine import Script
from src.engine.transcript import build_transcript_s3_key, persist_transcript

USER_ID = "11111111-1111-1111-1111-111111111111"
EPISODE_ID = "22222222-2222-2222-2222-222222222222"

SCRIPT = Script(
    title="What Retrieval-Augmented Generation Actually Fixes",
    summary="A two-host discussion of grounding a model in fetched documents.",
    turns=[
        {"speaker": "host", "text": "Welcome to The Signal Room."},
        {"speaker": "guest", "text": "Glad to be here. Let's get into it."},
    ],
)


def test_transcript_key_sits_beside_the_audio_under_the_tenant_prefix():
    """Bucket policy, IAM and lifecycle rules scope on ``podcasts/user-*``
    (issue #215) — the transcript must land inside that prefix too."""
    from src.tasks.podcast_generation import build_podcast_s3_key

    audio_key = build_podcast_s3_key(USER_ID, EPISODE_ID)
    transcript_key = build_transcript_s3_key(USER_ID, EPISODE_ID)

    assert transcript_key == f"podcasts/user-{USER_ID}/episode-{EPISODE_ID}.transcript.json"
    assert transcript_key.rsplit("/", 1)[0] == audio_key.rsplit("/", 1)[0]


def test_persist_uploads_to_s3_when_a_bucket_is_configured():
    s3 = MagicMock()

    with patch.object(settings, "AWS_S3_BUCKET", "episodes-bucket"), patch(
        "src.engine.transcript.boto3.client", return_value=s3
    ):
        path = persist_transcript(SCRIPT, USER_ID, EPISODE_ID)

    assert path == build_transcript_s3_key(USER_ID, EPISODE_ID)
    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "episodes-bucket"
    assert kwargs["Key"] == path
    assert kwargs["ContentType"] == "application/json"
    # The body is the script itself, and it round-trips.
    assert Script.model_validate_json(kwargs["Body"]) == SCRIPT


def test_persist_falls_back_to_local_storage_without_a_bucket(tmp_path):
    with patch.object(settings, "AWS_S3_BUCKET", None), patch.object(
        settings, "LOCAL_AUDIO_STORAGE_PATH", str(tmp_path)
    ):
        path = persist_transcript(SCRIPT, USER_ID, EPISODE_ID)

    assert path == str(tmp_path / f"episode-{EPISODE_ID}.transcript.json")
    assert Script.model_validate_json(Path(path).read_text()) == SCRIPT


def test_local_fallback_creates_the_storage_directory(tmp_path):
    target = tmp_path / "does" / "not" / "exist"

    with patch.object(settings, "AWS_S3_BUCKET", None), patch.object(
        settings, "LOCAL_AUDIO_STORAGE_PATH", str(target)
    ):
        path = persist_transcript(SCRIPT, USER_ID, EPISODE_ID)

    assert target.is_dir()
    assert json.loads(Path(path).read_text())["title"] == SCRIPT.title


def test_persisted_json_is_readable_by_a_human_and_keeps_turn_order(tmp_path):
    with patch.object(settings, "AWS_S3_BUCKET", None), patch.object(
        settings, "LOCAL_AUDIO_STORAGE_PATH", str(tmp_path)
    ):
        path = persist_transcript(SCRIPT, USER_ID, EPISODE_ID)

    data = json.loads(Path(path).read_text())
    assert [t["speaker"] for t in data["turns"]] == ["host", "guest"]
    assert data["turns"][0]["text"] == "Welcome to The Signal Room."
    assert "\n" in Path(path).read_text()  # indented, not a single line


def test_s3_failure_propagates_rather_than_silently_losing_the_transcript():
    s3 = MagicMock()
    s3.put_object.side_effect = RuntimeError("bucket is on fire")

    with patch.object(settings, "AWS_S3_BUCKET", "episodes-bucket"), patch(
        "src.engine.transcript.boto3.client", return_value=s3
    ):
        with pytest.raises(RuntimeError, match="bucket is on fire"):
            persist_transcript(SCRIPT, USER_ID, EPISODE_ID)


@pytest.mark.parametrize(
    "user_id,episode_id",
    [
        (USER_ID, "../../../../etc/cron.d/pwned"),
        ("../../..", EPISODE_ID),
        (USER_ID, "/absolute/elsewhere"),
        (USER_ID, "not-a-uuid"),
        (USER_ID, None),
    ],
)
def test_non_uuid_ids_are_rejected_before_anything_is_written(
    user_id, episode_id, tmp_path
):
    """The local branch is a real filesystem join, where ".." is honoured and an
    absolute second component replaces the first — unlike the S3 key, where
    neither means anything. Both ids come from UUID columns, so this is free.
    """
    from src.engine.llm import EngineError

    with patch.object(settings, "AWS_S3_BUCKET", None), patch.object(
        settings, "LOCAL_AUDIO_STORAGE_PATH", str(tmp_path)
    ):
        with pytest.raises(EngineError, match="not a valid UUID"):
            persist_transcript(SCRIPT, user_id, episode_id)

    assert list(tmp_path.iterdir()) == [], "a file was written despite the bad id"


def test_traversal_in_an_id_cannot_escape_the_tenant_prefix_in_the_s3_key():
    from src.engine.llm import EngineError

    with pytest.raises(EngineError, match="not a valid UUID"):
        build_transcript_s3_key(USER_ID, "../../other-tenant/episode")
