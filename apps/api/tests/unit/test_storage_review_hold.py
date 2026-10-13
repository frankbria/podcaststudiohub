"""StorageService support for holding unreviewed episode audio (#626)."""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.services.storage_service import StorageService

KEY = "podcasts/user-u/episode-e.mp3"


def _service(client):
    service = StorageService(bucket_name="bucket", region_name="us-east-1")
    service.s3_client = client
    return service


def _not_found():
    return ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")


@pytest.mark.asyncio
async def test_object_metadata_returns_the_user_metadata():
    client = MagicMock()
    client.head_object.return_value = {"Metadata": {"content-review": "pending"}}

    assert await _service(client).object_metadata(KEY) == {"content-review": "pending"}
    client.head_object.assert_called_once_with(Bucket="bucket", Key=KEY)


@pytest.mark.asyncio
async def test_object_metadata_is_none_for_a_missing_object():
    client = MagicMock()
    client.head_object.side_effect = _not_found()

    assert await _service(client).object_metadata(KEY) is None


@pytest.mark.asyncio
async def test_clearing_the_hold_rewrites_metadata_in_place():
    client = MagicMock()
    client.head_object.return_value = {"Metadata": {"content-review": "pending"}, "ContentType": "audio/mpeg"}

    await _service(client).clear_content_review_hold(KEY)

    kwargs = client.copy_object.call_args.kwargs
    assert kwargs["Bucket"] == "bucket" and kwargs["Key"] == KEY
    assert kwargs["CopySource"] == {"Bucket": "bucket", "Key": KEY}
    assert kwargs["MetadataDirective"] == "REPLACE"
    assert kwargs["Metadata"] == {}
    assert kwargs["ContentType"] == "audio/mpeg"  # REPLACE would otherwise reset it


@pytest.mark.asyncio
async def test_clearing_a_hold_on_a_missing_object_is_a_no_op():
    client = MagicMock()
    client.head_object.side_effect = _not_found()

    await _service(client).clear_content_review_hold(KEY)

    client.copy_object.assert_not_called()
