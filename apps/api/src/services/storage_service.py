"""Storage service for S3 operations"""

from typing import Optional, BinaryIO
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

from ..config import settings


class StorageService:
    """Service for handling S3 storage operations"""

    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        region_name: str = "us-east-1",
    ):
        """
        Initialize S3 storage service

        Args:
            aws_access_key_id: AWS access key (uses settings.AWS_ACCESS_KEY_ID if not provided)
            aws_secret_access_key: AWS secret key (uses settings.AWS_SECRET_ACCESS_KEY if not provided)
            bucket_name: S3 bucket name (uses settings.S3_BUCKET_NAME if not provided)
            region_name: AWS region
        """
        self.aws_access_key_id = aws_access_key_id or getattr(settings, "AWS_ACCESS_KEY_ID", None)
        self.aws_secret_access_key = aws_secret_access_key or getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
        self.bucket_name = bucket_name or getattr(settings, "S3_BUCKET_NAME", None)
        self.region_name = region_name

        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
        )

    async def upload_file(
        self,
        file_path: str,
        s3_key: str,
        content_type: Optional[str] = None,
        public: bool = False,
    ) -> str:
        """
        Upload file to S3

        Args:
            file_path: Local file path to upload
            s3_key: S3 object key (path in bucket)
            content_type: MIME type of the file
            public: Make file publicly accessible

        Returns:
            Public URL of the uploaded file
        """
        extra_args = {}

        if content_type:
            extra_args["ContentType"] = content_type

        if public:
            extra_args["ACL"] = "public-read"

        try:
            self.s3_client.upload_file(
                Filename=file_path,
                Bucket=self.bucket_name,
                Key=s3_key,
                ExtraArgs=extra_args if extra_args else None,
            )

            # Generate public URL
            url = f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{s3_key}"
            return url

        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {str(e)}")

    async def download_file(self, s3_key: str, local_path: str) -> str:
        """
        Download file from S3

        Args:
            s3_key: S3 object key
            local_path: Local destination path

        Returns:
            Local file path
        """
        try:
            self.s3_client.download_file(
                Bucket=self.bucket_name,
                Key=s3_key,
                Filename=local_path,
            )
            return local_path

        except ClientError as e:
            raise Exception(f"Failed to download file from S3: {str(e)}")

    async def delete_file(self, s3_key: str) -> None:
        """
        Delete file from S3

        Args:
            s3_key: S3 object key
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key,
            )

        except ClientError as e:
            raise Exception(f"Failed to delete file from S3: {str(e)}")

    async def generate_presigned_url(
        self,
        s3_key: str,
        expiration: int = 3600,
    ) -> str:
        """
        Generate presigned URL for temporary access

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": s3_key,
                },
                ExpiresIn=expiration,
            )
            return url

        except ClientError as e:
            raise Exception(f"Failed to generate presigned URL: {str(e)}")

    async def file_exists(self, s3_key: str) -> bool:
        """
        Check if file exists in S3

        Args:
            s3_key: S3 object key

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key,
            )
            return True

        except ClientError:
            return False
