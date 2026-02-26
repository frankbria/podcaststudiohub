"""
Celery tasks for S3 file uploads
"""
import os
import logging
from celery import Task
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError

from src.worker import celery_app
from src.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="upload_to_s3", time_limit=300)
def upload_to_s3_task(
    self: Task,
    file_path: str,
    s3_key: str,
    bucket_name: str,
    content_type: str = "audio/mpeg"
) -> Dict[str, Any]:
    """
    Upload a file to AWS S3.

    Args:
        self: Celery task instance
        file_path: Local file path to upload
        s3_key: S3 object key (path in bucket)
        bucket_name: S3 bucket name
        content_type: MIME type of the file

    Returns:
        Dictionary with upload results including s3_url, s3_key, file_size_bytes
    """
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 0,
                'status': 'Starting S3 upload...'
            }
        )

        # Initialize S3 client
        s3_client = boto3.client('s3')

        # Get file size for progress tracking
        file_size = os.path.getsize(file_path)

        # Upload with progress callback
        def upload_progress(bytes_transferred):
            progress = int((bytes_transferred / file_size) * 100)
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': progress,
                    'status': f'Uploading to S3... {progress}%'
                }
            )

        # Upload file
        s3_client.upload_file(
            file_path,
            bucket_name,
            s3_key,
            ExtraArgs={'ContentType': content_type},
            Callback=upload_progress
        )

        # Generate region-aware public URL
        region = settings.AWS_REGION
        if region == "us-east-1":
            # us-east-1 uses the legacy URL format without region subdomain
            s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
        else:
            s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"

        return {
            "status": "success",
            "s3_key": s3_key,
            "s3_url": s3_url,
            "file_size_bytes": file_size,
            "error": None
        }

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        NON_RETRYABLE_CODES = frozenset({
            "NoSuchBucket", "InvalidAccessKeyId",
            "SignatureDoesNotMatch", "AccessDenied",
        })
        if error_code in NON_RETRYABLE_CODES:
            # Re-raise non-retryable errors so they are never retried,
            # even if autoretry_for is added to this task in the future.
            logger.error(f"S3 upload failed with non-retryable error ({error_code}): {e}")
            raise
        logger.error(f"S3 upload failed for {file_path}: {str(e)}")
        return {
            "status": "failed",
            "s3_key": None,
            "s3_url": None,
            "file_size_bytes": 0,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"S3 upload failed for {file_path}: {str(e)}")
        return {
            "status": "failed",
            "s3_key": None,
            "s3_url": None,
            "file_size_bytes": 0,
            "error": str(e)
        }
