"""
Celery task for RSS feed generation, validation, and S3 upload.

Orchestrates the full RSS lifecycle: generate XML, validate against
platform standards, upload to S3, and update the RSSFeed database record.
"""

import logging
import tempfile
import os
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from celery import Task
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from src.worker import celery_app
from src.config import settings
from src.database import SyncSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_rss_feed", time_limit=300)
def generate_rss_feed_task(
	self: Task,
	project_id: str,
	tenant_id: str,
) -> Dict[str, Any]:
	"""
	Generate and validate RSS feed for a project, then upload to S3.

	This task:
	1. Generates RSS 2.0 XML using RSSGenerationService
	2. Validates the feed against Apple Podcasts, Spotify, and Google Podcasts
	3. Uploads the XML to S3 with public-read access
	4. Updates the RSSFeed database record with results

	Args:
		self: Celery task instance (for state updates)
		project_id: UUID string of the project
		tenant_id: UUID string of the tenant (for RLS context)

	Returns:
		Dict with results:
		{
			"status": "success" | "failed",
			"public_url": Optional[str],
			"validation_status": Optional[dict],
			"error": Optional[str]
		}
	"""
	from src.services.rss_generation_service import RSSGenerationService
	from src.services.rss_validator import RSSValidatorService
	from src.models.rss_feed import RSSFeed
	from src.models.project import Project
	from src.models.episode import Episode

	self.update_state(
		state="PROGRESS",
		meta={"status": "Generating RSS feed...", "progress": 10},
	)

	db = SyncSessionLocal()
	try:
		# Set tenant context for RLS
		db.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))

		# Fetch project with user relationship
		project = db.execute(
			select(Project)
			.options(joinedload(Project.user))
			.where(Project.id == UUID(project_id))
		).scalar_one_or_none()

		if project is None:
			return {
				"status": "failed",
				"public_url": None,
				"validation_status": None,
				"error": f"Project {project_id} not found",
			}

		# Validate podcast metadata has required fields
		rss_service = RSSGenerationService()
		try:
			rss_service._validate_podcast_metadata(project.podcast_metadata or {})
		except ValueError as e:
			return {
				"status": "failed",
				"public_url": None,
				"validation_status": None,
				"error": str(e),
			}

		# Fetch completed episodes ordered newest-first
		episodes = list(
			db.execute(
				select(Episode)
				.where(
					Episode.project_id == UUID(project_id),
					Episode.generation_status == "complete",
				)
				.order_by(Episode.created_at.desc())
			).scalars().all()
		)

		# Build RSS XML
		xml_content = rss_service._build_rss_document(project, episodes)

		self.update_state(
			state="PROGRESS",
			meta={"status": "Validating RSS feed...", "progress": 40},
		)

		# Validate generated feed
		validator = RSSValidatorService()
		validation_result = validator.validate_feed(xml_content)

		self.update_state(
			state="PROGRESS",
			meta={"status": "Uploading to S3...", "progress": 60},
		)

		# Upload RSS XML to S3 synchronously
		s3_key = f"rss-feeds/{project_id}/feed.xml"
		public_url = _upload_rss_xml_to_s3(s3_key, xml_content)

		self.update_state(
			state="PROGRESS",
			meta={"status": "Updating database...", "progress": 85},
		)

		# Get or create RSSFeed record
		rss_feed = db.execute(
			select(RSSFeed).where(RSSFeed.project_id == UUID(project_id))
		).scalar_one_or_none()

		if rss_feed is None:
			rss_feed = RSSFeed(
				project_id=UUID(project_id),
				tenant_id=UUID(tenant_id),
				validation_status={},
			)
			db.add(rss_feed)
			db.flush()

		rss_feed.s3_key = s3_key
		rss_feed.public_url = public_url
		rss_feed.validation_status = validation_result
		rss_feed.last_generated = datetime.now(timezone.utc)
		db.commit()

		return {
			"status": "success",
			"public_url": public_url,
			"validation_status": validation_result,
			"error": None,
		}

	except Exception as e:
		db.rollback()
		logger.error(
			f"RSS generation task failed for project {project_id}: {e}",
			exc_info=True,
		)
		return {
			"status": "failed",
			"public_url": None,
			"validation_status": None,
			"error": str(e),
		}
	finally:
		db.close()


def _upload_rss_xml_to_s3(s3_key: str, xml_content: str) -> str:
	"""
	Upload RSS XML string to S3 with public-read access.

	Uses a temporary file for the upload then cleans it up.

	Args:
		s3_key: S3 object key (path in bucket) for the RSS feed
		xml_content: RSS XML string to upload

	Returns:
		Public URL of the uploaded RSS feed

	Raises:
		Exception: If S3 upload fails
	"""
	bucket_name = getattr(settings, "S3_BUCKET_NAME", None)
	region = getattr(settings, "AWS_REGION", "us-east-1")

	s3_client = boto3.client(
		"s3",
		aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
		aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
		region_name=region,
	)

	with tempfile.NamedTemporaryFile(
		mode="w",
		suffix=".xml",
		delete=False,
		encoding="utf-8",
	) as tmp:
		tmp.write(xml_content)
		tmp_path = tmp.name

	try:
		s3_client.upload_file(
			Filename=tmp_path,
			Bucket=bucket_name,
			Key=s3_key,
			ExtraArgs={
				"ContentType": "application/rss+xml",
				"ACL": "public-read",
			},
		)
	except ClientError as e:
		raise Exception(f"Failed to upload RSS feed to S3: {e}") from e
	finally:
		if os.path.exists(tmp_path):
			os.unlink(tmp_path)

	# Build public URL
	if region == "us-east-1":
		return f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
	return f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
