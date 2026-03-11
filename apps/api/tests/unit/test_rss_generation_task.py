"""
Unit tests for the generate_rss_feed Celery task.

Tests task orchestration: project fetch, XML generation, validation,
S3 upload, and database update. All external dependencies are mocked.
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.tasks.rss_generation import generate_rss_feed_task, _upload_rss_xml_to_s3


# ============================================================================
# HELPERS
# ============================================================================

def _make_project(project_id=None, tenant_id=None):
	"""Build a mock Project with valid podcast metadata."""
	project = MagicMock()
	project.id = project_id or uuid4()
	project.tenant_id = tenant_id or uuid4()
	project.name = "Test Podcast"
	project.podcast_metadata = {
		"show_title": "Test Podcast",
		"author": "Test Author",
		"description": "A great podcast",
		"language": "en-us",
		"explicit": False,
		"category": "Technology",
		"artwork_url": "https://example.com/art.jpg",
	}
	project.user = MagicMock()
	project.user.email = "author@example.com"
	return project


def _make_episode(project_id=None):
	"""Build a mock Episode in 'complete' status."""
	ep = MagicMock()
	ep.id = uuid4()
	ep.project_id = project_id or uuid4()
	ep.generation_status = "complete"
	ep.s3_url = "https://s3.example.com/ep1.mp3"
	ep.file_size_bytes = 5_000_000
	ep.duration_seconds = 300
	ep.created_at = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
	ep.episode_metadata = {
		"title": "Episode 1",
		"description": "First episode",
		"episode_number": 1,
	}
	return ep


def _make_rss_feed():
	"""Build a mock RSSFeed record."""
	feed = MagicMock()
	feed.id = uuid4()
	feed.s3_key = None
	feed.public_url = None
	feed.validation_status = {}
	feed.last_generated = None
	return feed


def _run_task(project_id: str, tenant_id: str, db_mock: MagicMock, **extra_patches) -> dict:
	"""
	Helper to run the generate_rss_feed Celery task with mocked deps.

	Patches SyncSessionLocal and update_state. Additional patches can be
	passed as keyword arguments.
	"""
	with patch("src.tasks.rss_generation.SyncSessionLocal", return_value=db_mock), \
	     patch.object(generate_rss_feed_task, "update_state"):
		ctx = {}
		for name, mock in extra_patches.items():
			ctx[name] = mock
		# Run via .run() which binds self=task
		result = generate_rss_feed_task.run(project_id, tenant_id)
	return result


# ============================================================================
# TASK TESTS
# ============================================================================

class TestGenerateRssFeedTask:
	"""Tests for generate_rss_feed_task Celery task."""

	def test_task_returns_success_on_valid_project(self):
		"""Test that the task returns success with public_url."""
		project_id = str(uuid4())
		tenant_id = str(uuid4())
		project = _make_project(project_id=project_id)
		episode = _make_episode(project_id=project_id)
		rss_feed = _make_rss_feed()

		execute_results = []

		def execute_side_effect(query):
			result = MagicMock()
			call_num = len(execute_results)
			execute_results.append(call_num)

			if call_num == 0:
				# SET LOCAL tenant context
				return result
			elif call_num == 1:
				# Project query
				result.scalar_one_or_none.return_value = project
				return result
			elif call_num == 2:
				# Episodes query
				result.scalars.return_value.all.return_value = [episode]
				return result
			else:
				# RSSFeed query
				result.scalar_one_or_none.return_value = rss_feed
				return result

		mock_db = MagicMock()
		mock_db.execute.side_effect = execute_side_effect
		mock_db.add = MagicMock()
		mock_db.flush = MagicMock()
		mock_db.commit = MagicMock()
		mock_db.rollback = MagicMock()
		mock_db.close = MagicMock()

		with patch("src.tasks.rss_generation.SyncSessionLocal", return_value=mock_db), \
		     patch.object(generate_rss_feed_task, "update_state"), \
		     patch("src.tasks.rss_generation._upload_rss_xml_to_s3",
		           return_value="https://bucket.s3.amazonaws.com/rss-feeds/test/feed.xml"):
			result = generate_rss_feed_task.run(project_id, tenant_id)

		assert result["status"] == "success"
		assert result["public_url"] == "https://bucket.s3.amazonaws.com/rss-feeds/test/feed.xml"
		assert result["error"] is None
		assert "validation_status" in result

	def test_task_returns_failure_when_project_not_found(self):
		"""Test that the task returns failure when project does not exist."""
		project_id = str(uuid4())
		tenant_id = str(uuid4())

		execute_results = []

		def execute_side_effect(query):
			result = MagicMock()
			call_num = len(execute_results)
			execute_results.append(call_num)

			if call_num == 0:
				return result
			else:
				result.scalar_one_or_none.return_value = None
				return result

		mock_db = MagicMock()
		mock_db.execute.side_effect = execute_side_effect
		mock_db.close = MagicMock()

		with patch("src.tasks.rss_generation.SyncSessionLocal", return_value=mock_db), \
		     patch.object(generate_rss_feed_task, "update_state"):
			result = generate_rss_feed_task.run(project_id, tenant_id)

		assert result["status"] == "failed"
		assert result["public_url"] is None
		assert "not found" in result["error"]

	def test_task_returns_failure_on_invalid_metadata(self):
		"""Test that the task returns failure when podcast_metadata is invalid."""
		project_id = str(uuid4())
		tenant_id = str(uuid4())
		project = _make_project(project_id=project_id)
		# Remove required field
		project.podcast_metadata = {
			"author": "Author",
			"description": "Desc",
			# missing show_title
		}

		execute_results = []

		def execute_side_effect(query):
			result = MagicMock()
			call_num = len(execute_results)
			execute_results.append(call_num)
			if call_num == 0:
				return result
			result.scalar_one_or_none.return_value = project
			return result

		mock_db = MagicMock()
		mock_db.execute.side_effect = execute_side_effect
		mock_db.close = MagicMock()

		with patch("src.tasks.rss_generation.SyncSessionLocal", return_value=mock_db), \
		     patch.object(generate_rss_feed_task, "update_state"):
			result = generate_rss_feed_task.run(project_id, tenant_id)

		assert result["status"] == "failed"
		assert result["error"] is not None
		assert "show_title" in result["error"]

	def test_task_creates_new_rss_feed_record(self):
		"""Test that the task creates a new RSSFeed record if one doesn't exist."""
		from src.models.rss_feed import RSSFeed

		project_id = str(uuid4())
		tenant_id = str(uuid4())
		project = _make_project(project_id=project_id)
		added_objects = []

		execute_results = []

		def execute_side_effect(query):
			result = MagicMock()
			call_num = len(execute_results)
			execute_results.append(call_num)

			if call_num == 0:
				return result
			elif call_num == 1:
				result.scalar_one_or_none.return_value = project
				return result
			elif call_num == 2:
				result.scalars.return_value.all.return_value = []
				return result
			else:
				result.scalar_one_or_none.return_value = None
				return result

		mock_db = MagicMock()
		mock_db.execute.side_effect = execute_side_effect
		mock_db.add.side_effect = lambda obj: added_objects.append(obj)
		mock_db.flush = MagicMock()
		mock_db.commit = MagicMock()
		mock_db.rollback = MagicMock()
		mock_db.close = MagicMock()

		with patch("src.tasks.rss_generation.SyncSessionLocal", return_value=mock_db), \
		     patch.object(generate_rss_feed_task, "update_state"), \
		     patch("src.tasks.rss_generation._upload_rss_xml_to_s3",
		           return_value="https://bucket.s3.amazonaws.com/feed.xml"):
			generate_rss_feed_task.run(project_id, tenant_id)

		assert any(isinstance(obj, RSSFeed) for obj in added_objects)

	def test_task_handles_s3_upload_failure(self):
		"""Test that S3 upload failure is caught and returned as failed status."""
		project_id = str(uuid4())
		tenant_id = str(uuid4())
		project = _make_project(project_id=project_id)

		execute_results = []

		def execute_side_effect(query):
			result = MagicMock()
			call_num = len(execute_results)
			execute_results.append(call_num)

			if call_num == 0:
				return result
			elif call_num == 1:
				result.scalar_one_or_none.return_value = project
				return result
			else:
				result.scalars.return_value.all.return_value = []
				return result

		mock_db = MagicMock()
		mock_db.execute.side_effect = execute_side_effect
		mock_db.rollback = MagicMock()
		mock_db.close = MagicMock()

		with patch("src.tasks.rss_generation.SyncSessionLocal", return_value=mock_db), \
		     patch.object(generate_rss_feed_task, "update_state"), \
		     patch("src.tasks.rss_generation._upload_rss_xml_to_s3",
		           side_effect=Exception("S3 upload failed")):
			result = generate_rss_feed_task.run(project_id, tenant_id)

		assert result["status"] == "failed"
		assert "S3 upload failed" in result["error"]


# ============================================================================
# UPLOAD HELPER TESTS
# ============================================================================

class TestUploadRssXmlToS3:
	"""Tests for the _upload_rss_xml_to_s3 helper function."""

	def test_upload_returns_us_east_1_url(self):
		"""Test that us-east-1 uses legacy URL format."""
		s3_key = "rss-feeds/project-123/feed.xml"
		xml_content = "<rss>test</rss>"

		mock_s3 = MagicMock()

		with patch("src.tasks.rss_generation.boto3.client", return_value=mock_s3), \
		     patch("src.tasks.rss_generation.settings") as mock_settings:
			mock_settings.S3_BUCKET_NAME = "my-podcast-bucket"
			mock_settings.AWS_REGION = "us-east-1"
			mock_settings.AWS_ACCESS_KEY_ID = "test-key"
			mock_settings.AWS_SECRET_ACCESS_KEY = "test-secret"

			url = _upload_rss_xml_to_s3(s3_key, xml_content)

		assert "my-podcast-bucket" in url
		assert "feed.xml" in url
		assert url.startswith("https://")
		# us-east-1 legacy format: no region subdomain
		assert "us-east-1" not in url

	def test_upload_returns_regional_url(self):
		"""Test that non-us-east-1 regions use regional URL format."""
		s3_key = "rss-feeds/project-456/feed.xml"
		xml_content = "<rss>test</rss>"

		mock_s3 = MagicMock()

		with patch("src.tasks.rss_generation.boto3.client", return_value=mock_s3), \
		     patch("src.tasks.rss_generation.settings") as mock_settings:
			mock_settings.S3_BUCKET_NAME = "my-bucket"
			mock_settings.AWS_REGION = "eu-west-1"
			mock_settings.AWS_ACCESS_KEY_ID = "key"
			mock_settings.AWS_SECRET_ACCESS_KEY = "secret"

			url = _upload_rss_xml_to_s3(s3_key, xml_content)

		assert "eu-west-1" in url
		assert "my-bucket" in url

	def test_upload_uses_rss_xml_content_type(self):
		"""Test that upload sets application/rss+xml content type."""
		s3_key = "rss-feeds/project-123/feed.xml"
		xml_content = "<rss>test</rss>"

		mock_s3 = MagicMock()

		with patch("src.tasks.rss_generation.boto3.client", return_value=mock_s3), \
		     patch("src.tasks.rss_generation.settings") as mock_settings:
			mock_settings.S3_BUCKET_NAME = "my-bucket"
			mock_settings.AWS_REGION = "us-west-2"
			mock_settings.AWS_ACCESS_KEY_ID = "key"
			mock_settings.AWS_SECRET_ACCESS_KEY = "secret"

			_upload_rss_xml_to_s3(s3_key, xml_content)

		assert mock_s3.upload_file.called
		call_kwargs = mock_s3.upload_file.call_args[1]
		extra_args = call_kwargs.get("ExtraArgs", {})
		assert extra_args.get("ContentType") == "application/rss+xml"

	def test_upload_sets_public_read_acl(self):
		"""Test that upload sets public-read ACL for RSS feeds."""
		s3_key = "rss-feeds/project-123/feed.xml"
		xml_content = "<rss>test</rss>"

		mock_s3 = MagicMock()

		with patch("src.tasks.rss_generation.boto3.client", return_value=mock_s3), \
		     patch("src.tasks.rss_generation.settings") as mock_settings:
			mock_settings.S3_BUCKET_NAME = "my-bucket"
			mock_settings.AWS_REGION = "us-east-1"
			mock_settings.AWS_ACCESS_KEY_ID = "key"
			mock_settings.AWS_SECRET_ACCESS_KEY = "secret"

			_upload_rss_xml_to_s3(s3_key, xml_content)

		call_kwargs = mock_s3.upload_file.call_args[1]
		extra_args = call_kwargs.get("ExtraArgs", {})
		assert extra_args.get("ACL") == "public-read"
