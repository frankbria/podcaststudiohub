"""
Unit tests for StorageService using aioboto3 for truly async S3 operations.
All tests use AsyncMock / MagicMock to avoid requiring real AWS credentials.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client_error(code: str = "InternalError", message: str = "error") -> ClientError:
	return ClientError({"Error": {"Code": code, "Message": message}}, "Operation")


def _make_storage_service(bucket: str = "test-bucket", region: str = "us-east-1"):
	"""Return a StorageService with dummy credentials (no real AWS calls)."""
	from src.services.storage_service import StorageService

	return StorageService(
		aws_access_key_id="AKIATEST",
		aws_secret_access_key="secret",
		bucket_name=bucket,
		region_name=region,
	)


def _mock_client_ctx(mock_client: AsyncMock):
	"""Return a mock async context manager that yields *mock_client*."""
	ctx = MagicMock()
	ctx.__aenter__ = AsyncMock(return_value=mock_client)
	ctx.__aexit__ = AsyncMock(return_value=None)
	return ctx


# ---------------------------------------------------------------------------
# StorageService initialisation
# ---------------------------------------------------------------------------

class TestStorageServiceInit:
	def test_uses_provided_credentials(self):
		svc = _make_storage_service()
		assert svc.aws_access_key_id == "AKIATEST"
		assert svc.aws_secret_access_key == "secret"
		assert svc.bucket_name == "test-bucket"
		assert svc.region_name == "us-east-1"

	def test_creates_aioboto3_session(self):
		import aioboto3
		svc = _make_storage_service()
		assert isinstance(svc.session, aioboto3.Session)

	def test_falls_back_to_settings_for_bucket(self):
		from src.services.storage_service import StorageService

		with patch("src.services.storage_service.settings") as mock_settings:
			mock_settings.AWS_S3_BUCKET = "settings-bucket"
			mock_settings.AWS_ACCESS_KEY_ID = None
			mock_settings.AWS_SECRET_ACCESS_KEY = None
			svc = StorageService()

		assert svc.bucket_name == "settings-bucket"


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------

class TestUploadFile:
	@pytest.mark.asyncio
	async def test_upload_returns_public_url(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.upload_file = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			url = await svc.upload_file("/tmp/audio.mp3", "podcasts/ep1.mp3")

		assert url == "https://test-bucket.s3.us-east-1.amazonaws.com/podcasts/ep1.mp3"

	@pytest.mark.asyncio
	async def test_upload_passes_content_type(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.upload_file = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			await svc.upload_file("/tmp/audio.mp3", "ep1.mp3", content_type="audio/mpeg")

		mock_client.upload_file.assert_awaited_once()
		call_kwargs = mock_client.upload_file.call_args.kwargs
		assert call_kwargs["ExtraArgs"] == {"ContentType": "audio/mpeg"}

	@pytest.mark.asyncio
	async def test_upload_passes_public_acl(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.upload_file = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			await svc.upload_file("/tmp/audio.mp3", "ep1.mp3", public=True)

		call_kwargs = mock_client.upload_file.call_args.kwargs
		assert call_kwargs["ExtraArgs"] == {"ACL": "public-read"}

	@pytest.mark.asyncio
	async def test_upload_no_extra_args_when_not_needed(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.upload_file = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			await svc.upload_file("/tmp/audio.mp3", "ep1.mp3")

		call_kwargs = mock_client.upload_file.call_args.kwargs
		assert call_kwargs["ExtraArgs"] is None

	@pytest.mark.asyncio
	async def test_upload_raises_on_client_error(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.upload_file = AsyncMock(side_effect=_make_client_error())

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with pytest.raises(Exception, match="Failed to upload file to S3"):
				await svc.upload_file("/tmp/audio.mp3", "ep1.mp3")

	@pytest.mark.asyncio
	async def test_upload_raises_on_timeout(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()

		async def slow_upload(**kwargs):
			await asyncio.sleep(999)

		mock_client.upload_file = slow_upload

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
				with pytest.raises(Exception, match="5-minute timeout"):
					await svc.upload_file("/tmp/audio.mp3", "ep1.mp3")


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------

class TestDownloadFile:
	@pytest.mark.asyncio
	async def test_download_returns_local_path(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.download_file = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			result = await svc.download_file("podcasts/ep1.mp3", "/tmp/ep1.mp3")

		assert result == "/tmp/ep1.mp3"

	@pytest.mark.asyncio
	async def test_download_calls_client_with_correct_args(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.download_file = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			await svc.download_file("podcasts/ep1.mp3", "/tmp/ep1.mp3")

		mock_client.download_file.assert_awaited_once_with(
			Bucket="test-bucket",
			Key="podcasts/ep1.mp3",
			Filename="/tmp/ep1.mp3",
		)

	@pytest.mark.asyncio
	async def test_download_raises_on_client_error(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.download_file = AsyncMock(side_effect=_make_client_error())

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with pytest.raises(Exception, match="Failed to download file from S3"):
				await svc.download_file("ep1.mp3", "/tmp/ep1.mp3")

	@pytest.mark.asyncio
	async def test_download_raises_on_timeout(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.download_file = AsyncMock()

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
				with pytest.raises(Exception, match="5-minute timeout"):
					await svc.download_file("ep1.mp3", "/tmp/ep1.mp3")


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------

class TestDeleteFile:
	@pytest.mark.asyncio
	async def test_delete_calls_delete_object(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.delete_object = AsyncMock(return_value=None)

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			await svc.delete_file("podcasts/ep1.mp3")

		mock_client.delete_object.assert_awaited_once_with(
			Bucket="test-bucket",
			Key="podcasts/ep1.mp3",
		)

	@pytest.mark.asyncio
	async def test_delete_raises_on_client_error(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.delete_object = AsyncMock(side_effect=_make_client_error())

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with pytest.raises(Exception, match="Failed to delete file from S3"):
				await svc.delete_file("podcasts/ep1.mp3")

	@pytest.mark.asyncio
	async def test_delete_raises_on_timeout(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.delete_object = AsyncMock()

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
				with pytest.raises(Exception, match="60-second timeout"):
					await svc.delete_file("ep1.mp3")


# ---------------------------------------------------------------------------
# generate_presigned_url
# ---------------------------------------------------------------------------

class TestGeneratePresignedUrl:
	@pytest.mark.asyncio
	async def test_returns_presigned_url(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.generate_presigned_url = AsyncMock(return_value="https://presigned.example.com/key")

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			url = await svc.generate_presigned_url("podcasts/ep1.mp3")

		assert url == "https://presigned.example.com/key"

	@pytest.mark.asyncio
	async def test_passes_correct_params(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.generate_presigned_url = AsyncMock(return_value="https://presigned.example.com/key")

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			await svc.generate_presigned_url("podcasts/ep1.mp3", expiration=7200)

		mock_client.generate_presigned_url.assert_awaited_once_with(
			ClientMethod="get_object",
			Params={"Bucket": "test-bucket", "Key": "podcasts/ep1.mp3"},
			ExpiresIn=7200,
		)

	@pytest.mark.asyncio
	async def test_raises_on_client_error(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.generate_presigned_url = AsyncMock(side_effect=_make_client_error())

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with pytest.raises(Exception, match="Failed to generate presigned URL"):
				await svc.generate_presigned_url("ep1.mp3")

	@pytest.mark.asyncio
	async def test_raises_on_timeout(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.generate_presigned_url = AsyncMock()

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
				with pytest.raises(Exception, match="30-second timeout"):
					await svc.generate_presigned_url("ep1.mp3")


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------

class TestFileExists:
	@pytest.mark.asyncio
	async def test_returns_true_when_file_exists(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.head_object = AsyncMock(return_value={})

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			result = await svc.file_exists("podcasts/ep1.mp3")

		assert result is True

	@pytest.mark.asyncio
	async def test_returns_false_when_file_not_found(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.head_object = AsyncMock(side_effect=_make_client_error("404"))

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			result = await svc.file_exists("podcasts/ep1.mp3")

		assert result is False

	@pytest.mark.asyncio
	async def test_raises_on_timeout(self):
		svc = _make_storage_service()
		mock_client = AsyncMock()
		mock_client.head_object = AsyncMock()

		with patch.object(svc, "_client", return_value=_mock_client_ctx(mock_client)):
			with patch("asyncio.timeout", side_effect=asyncio.TimeoutError):
				with pytest.raises(Exception, match="30-second timeout"):
					await svc.file_exists("ep1.mp3")


# ---------------------------------------------------------------------------
# Concurrency test
# ---------------------------------------------------------------------------

class TestConcurrentOperations:
	@pytest.mark.asyncio
	async def test_ten_concurrent_uploads_complete_without_blocking(self):
		"""10 concurrent upload calls should all complete; none should block the others."""
		svc = _make_storage_service()

		call_order: list[int] = []

		def make_mock_client(index: int):
			mock_client = AsyncMock()

			async def fake_upload(**kwargs):
				call_order.append(index)
				await asyncio.sleep(0)  # yield to event loop

			mock_client.upload_file = fake_upload
			return mock_client

		async def upload_one(index: int):
			mc = make_mock_client(index)
			with patch.object(svc, "_client", return_value=_mock_client_ctx(mc)):
				await svc.upload_file(f"/tmp/file_{index}.mp3", f"key_{index}.mp3")

		await asyncio.gather(*[upload_one(i) for i in range(10)])

		assert len(call_order) == 10, "All 10 uploads should have completed"
