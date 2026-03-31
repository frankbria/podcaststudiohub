"""
Unit tests for StorageService (S3 operations).

StorageService is always mocked in integration tests (test_download_endpoint,
test_rss_feed, test_audio_snippets), so all its lines are genuinely uncovered
in CI. These unit tests mock boto3 to exercise every method.

Tests cover:
- __init__: S3 client initialization with credentials from args/settings
- upload_file: with content_type, with public ACL, ClientError raises
- download_file: success, ClientError raises
- delete_file: success, ClientError raises
- generate_presigned_url: success, ClientError raises
- file_exists: exists (True), not exists (False)
"""

import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src.services.storage_service import StorageService


def _make_client_error(code="NoSuchKey"):
	"""Build a minimal ClientError for testing."""
	return ClientError({"Error": {"Code": code, "Message": "Test error"}}, "test_op")


@pytest.fixture
def mock_boto3_client():
	"""Patch boto3.client so StorageService can be instantiated without AWS creds."""
	with patch("src.services.storage_service.boto3.client") as mock_client:
		mock_s3 = MagicMock()
		mock_client.return_value = mock_s3
		yield mock_s3


@pytest.fixture
def service(mock_boto3_client):
	return StorageService(
		aws_access_key_id="test-key",
		aws_secret_access_key="test-secret",
		bucket_name="test-bucket",
	)


# ===========================================================================
# __init__
# ===========================================================================


def test_init_sets_bucket_name(service):
	assert service.bucket_name == "test-bucket"


def test_init_sets_region(mock_boto3_client):
	with patch("src.services.storage_service.boto3.client") as mock_client:
		mock_client.return_value = MagicMock()
		svc = StorageService(bucket_name="b", region_name="eu-west-1")
	assert svc.region_name == "eu-west-1"


# ===========================================================================
# upload_file
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_file_success_returns_url(service, mock_boto3_client):
	mock_boto3_client.upload_file.return_value = None
	url = await service.upload_file("/tmp/test.mp3", "path/to/key.mp3")
	assert "test-bucket" in url
	assert "key.mp3" in url


@pytest.mark.asyncio
async def test_upload_file_with_content_type(service, mock_boto3_client):
	await service.upload_file("/tmp/test.mp3", "key.mp3", content_type="audio/mpeg")
	call_kwargs = mock_boto3_client.upload_file.call_args[1]
	assert call_kwargs["ExtraArgs"]["ContentType"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_upload_file_with_public_acl(service, mock_boto3_client):
	await service.upload_file("/tmp/test.mp3", "key.mp3", public=True)
	call_kwargs = mock_boto3_client.upload_file.call_args[1]
	assert call_kwargs["ExtraArgs"]["ACL"] == "public-read"


@pytest.mark.asyncio
async def test_upload_file_client_error_raises(service, mock_boto3_client):
	mock_boto3_client.upload_file.side_effect = _make_client_error("AccessDenied")
	with pytest.raises(Exception, match="Failed to upload"):
		await service.upload_file("/tmp/test.mp3", "key.mp3")


# ===========================================================================
# download_file
# ===========================================================================


@pytest.mark.asyncio
async def test_download_file_success_returns_local_path(service, mock_boto3_client):
	mock_boto3_client.download_file.return_value = None
	result = await service.download_file("key.mp3", "/tmp/local.mp3")
	assert result == "/tmp/local.mp3"


@pytest.mark.asyncio
async def test_download_file_client_error_raises(service, mock_boto3_client):
	mock_boto3_client.download_file.side_effect = _make_client_error()
	with pytest.raises(Exception, match="Failed to download"):
		await service.download_file("key.mp3", "/tmp/local.mp3")


# ===========================================================================
# delete_file
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_file_success(service, mock_boto3_client):
	mock_boto3_client.delete_object.return_value = None
	await service.delete_file("key.mp3")  # Should not raise
	mock_boto3_client.delete_object.assert_called_once()


@pytest.mark.asyncio
async def test_delete_file_client_error_raises(service, mock_boto3_client):
	mock_boto3_client.delete_object.side_effect = _make_client_error()
	with pytest.raises(Exception, match="Failed to delete"):
		await service.delete_file("key.mp3")


# ===========================================================================
# generate_presigned_url
# ===========================================================================


@pytest.mark.asyncio
async def test_generate_presigned_url_success(service, mock_boto3_client):
	mock_boto3_client.generate_presigned_url.return_value = "https://presigned.url"
	url = await service.generate_presigned_url("key.mp3")
	assert url == "https://presigned.url"


@pytest.mark.asyncio
async def test_generate_presigned_url_client_error_raises(service, mock_boto3_client):
	mock_boto3_client.generate_presigned_url.side_effect = _make_client_error()
	with pytest.raises(Exception, match="Failed to generate presigned URL"):
		await service.generate_presigned_url("key.mp3")


# ===========================================================================
# file_exists
# ===========================================================================


@pytest.mark.asyncio
async def test_file_exists_returns_true_when_object_found(service, mock_boto3_client):
	mock_boto3_client.head_object.return_value = {"ContentLength": 1024}
	assert await service.file_exists("key.mp3") is True


@pytest.mark.asyncio
async def test_file_exists_returns_false_on_client_error(service, mock_boto3_client):
	mock_boto3_client.head_object.side_effect = _make_client_error("NoSuchKey")
	assert await service.file_exists("key.mp3") is False
