"""
Audio snippet service layer for business logic.

Provides CRUD operations for audio snippets with file upload to S3,
metadata extraction, pagination, filtering, and tenant isolation via RLS.
"""

import os
import tempfile
import uuid
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.audio_snippet import AudioSnippet
from ..models.project import Project
from ..schemas.audio_snippet import AudioSnippetUpdate
from ..utils.audio_utils import (
	validate_audio_format,
	validate_file_size,
	get_audio_duration,
	generate_s3_key,
	get_content_type,
	MAX_FILE_SIZE_BYTES,
	MIN_FILE_SIZE_BYTES,
)


async def upload_audio_snippet(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	file: UploadFile,
	name: str,
	snippet_type: str,
	description: Optional[str] = None,
	project_id: Optional[UUID] = None,
) -> AudioSnippet:
	"""
	Upload audio file and create snippet record.

	Validates file format and size, writes to a temp file, extracts audio
	metadata, uploads to S3, then creates the database record.

	Args:
		db: Database session
		user_id: ID of user uploading the snippet
		tenant_id: Tenant ID for isolation
		file: Uploaded audio file
		name: Snippet name
		snippet_type: Type of snippet (intro, outro, etc.)
		description: Optional description
		project_id: Optional project scope UUID

	Returns:
		Created AudioSnippet instance

	Raises:
		HTTPException: 413 if file too large, 422 if invalid format/corrupted, 404 if project not found
	"""
	# Validate project exists if provided
	if project_id is not None:
		project = await db.get(Project, project_id)
		if project is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Project not found"
			)

	# Validate file format early (before reading all bytes)
	filename = file.filename or ""
	try:
		file_ext = validate_audio_format(filename, file.content_type)
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=str(e)
		)

	# Read file contents
	file_bytes = await file.read()
	file_size = len(file_bytes)

	# Validate file size
	if file_size > MAX_FILE_SIZE_BYTES:
		raise HTTPException(
			status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
			detail=f"File too large ({file_size} bytes). Maximum allowed size is 50 MB"
		)
	try:
		validate_file_size(file_size)
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=str(e)
		)

	# Generate snippet ID upfront (needed for S3 key)
	snippet_id = uuid.uuid4()

	# Write to temp file for metadata extraction
	temp_path = None
	s3_key = None
	s3_url = None
	duration_seconds = None

	try:
		with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as tmp:
			tmp.write(file_bytes)
			temp_path = tmp.name

		# Extract audio metadata
		duration_seconds = get_audio_duration(temp_path)

		# Upload to S3 if configured
		s3_key = generate_s3_key(str(user_id), str(snippet_id), file_ext)
		s3_url = await _upload_to_s3(temp_path, s3_key, file_ext)

	except HTTPException:
		raise
	except Exception as e:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail=f"Failed to process audio file: {str(e)}"
		)
	finally:
		# Clean up temp file
		if temp_path and os.path.exists(temp_path):
			os.unlink(temp_path)

	# Create database record
	snippet = AudioSnippet(
		id=snippet_id,
		user_id=user_id,
		tenant_id=tenant_id,
		project_id=project_id,
		name=name,
		snippet_type=snippet_type,
		description=description,
		file_path=s3_key or f"audio-snippets/{snippet_id}.{file_ext}",
		s3_key=s3_key,
		s3_url=s3_url,
		duration_seconds=duration_seconds,
		file_size_bytes=file_size,
		file_format=file_ext,
	)

	db.add(snippet)
	await db.commit()
	return snippet


async def _upload_to_s3(file_path: str, s3_key: str, file_ext: str) -> Optional[str]:
	"""
	Upload file to S3 and return public URL.

	Returns None if S3 is not configured (development mode).

	Args:
		file_path: Local temp file path
		s3_key: S3 object key
		file_ext: File extension for content type

	Returns:
		S3 URL string or None if S3 not configured
	"""
	from ..config import settings
	from ..services.storage_service import StorageService

	bucket = getattr(settings, "AWS_S3_BUCKET", None)
	if not bucket:
		# S3 not configured - development mode, return None
		return None

	storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)
	content_type = get_content_type(file_ext)
	url = await storage.upload_file(
		file_path=file_path,
		s3_key=s3_key,
		content_type=content_type,
		public=True,
	)
	return url


async def get_audio_snippets(
	db: AsyncSession,
	snippet_type: Optional[str] = None,
	project_id: Optional[UUID] = None,
	search: Optional[str] = None,
	skip: int = 0,
	limit: int = 20,
) -> tuple[list[AudioSnippet], int]:
	"""
	Get paginated list of audio snippets.

	Optionally filter by snippet_type, project_id, and name search.
	RLS automatically filters by tenant.

	Args:
		db: Database session
		snippet_type: Optional snippet type filter
		project_id: Optional project ID filter
		search: Optional name search term
		skip: Number of records to skip
		limit: Maximum number of records to return

	Returns:
		Tuple of (snippets list, total count)
	"""
	query = select(AudioSnippet)

	if snippet_type:
		query = query.where(AudioSnippet.snippet_type == snippet_type)

	if project_id:
		query = query.where(AudioSnippet.project_id == project_id)

	if search:
		query = query.where(AudioSnippet.name.ilike(f"%{search}%"))

	# Get total count before pagination
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	# Get paginated results ordered by creation date descending
	query = query.offset(skip).limit(limit).order_by(AudioSnippet.created_at.desc())
	result = await db.execute(query)
	snippets = result.scalars().all()

	return list(snippets), total


async def get_audio_snippet_by_id(
	db: AsyncSession,
	snippet_id: UUID,
) -> Optional[AudioSnippet]:
	"""
	Get audio snippet by ID.

	RLS ensures user can only access snippets within their tenant.

	Args:
		db: Database session
		snippet_id: UUID of snippet to retrieve

	Returns:
		AudioSnippet instance or None if not found
	"""
	result = await db.execute(
		select(AudioSnippet).where(AudioSnippet.id == snippet_id)
	)
	return result.scalar_one_or_none()


async def update_audio_snippet(
	db: AsyncSession,
	snippet: AudioSnippet,
	update_data: AudioSnippetUpdate,
) -> AudioSnippet:
	"""
	Update audio snippet metadata.

	Only updates name, description, and snippet_type.
	Does not allow re-uploading the file (use delete + upload for that).

	Args:
		db: Database session
		snippet: Existing AudioSnippet instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated AudioSnippet instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)
	for field, value in update_dict.items():
		setattr(snippet, field, value)

	await db.commit()
	return snippet


async def delete_audio_snippet(
	db: AsyncSession,
	snippet: AudioSnippet,
) -> None:
	"""
	Delete audio snippet from S3 and database.

	Removes the S3 object first, then deletes the database record.
	S3 deletion errors are logged but do not block DB deletion.

	Args:
		db: Database session
		snippet: AudioSnippet instance to delete
	"""
	# Attempt to delete from S3 if configured
	if snippet.s3_key:
		try:
			from ..config import settings
			from ..services.storage_service import StorageService

			bucket = getattr(settings, "AWS_S3_BUCKET", None)
			if bucket:
				storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)
				await storage.delete_file(snippet.s3_key)
		except Exception:
			# Log but don't fail if S3 deletion fails
			import logging
			logging.getLogger(__name__).warning(
				f"Failed to delete S3 object {snippet.s3_key} for snippet {snippet.id}"
			)

	await db.delete(snippet)
	await db.commit()


async def generate_download_url(snippet: AudioSnippet, expiration: int = 3600) -> str:
	"""
	Generate a presigned S3 download URL for a snippet.

	Args:
		snippet: AudioSnippet instance
		expiration: URL expiration time in seconds (default 1 hour)

	Returns:
		Presigned S3 URL string

	Raises:
		HTTPException: 404 if snippet has no S3 key, 503 if S3 not configured
	"""
	if not snippet.s3_key:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="No file available for this snippet"
		)

	from ..config import settings
	from ..services.storage_service import StorageService

	bucket = getattr(settings, "AWS_S3_BUCKET", None)
	if not bucket:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="File storage not configured"
		)

	storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)
	url = await storage.generate_presigned_url(snippet.s3_key, expiration=expiration)
	return url
