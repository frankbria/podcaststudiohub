"""
Content source service layer for business logic.

Provides CRUD operations for content sources with episode validation, pagination,
and extraction status management. RLS ensures tenant isolation.
"""

import os
import tempfile
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from typing import Optional
from fastapi import HTTPException, UploadFile, status

from ..models import ContentSource, Episode
from ..schemas.content import ContentSourceCreate, ContentSourceUpdate
from ..utils.validators import (
    MAX_PDF_SIZE_BYTES,
    sanitize_filename,
    validate_pdf_format,
)


async def add_content_source(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    content_data: ContentSourceCreate
) -> ContentSource:
    """
    Create new content source for episode.

    Validates episode exists and belongs to user's tenant (RLS).
    Initial extraction_status is set to 'pending'.

    Args:
        db: Database session
        user_id: ID of user creating the content source (not stored directly)
        tenant_id: Tenant ID for isolation
        content_data: Content source creation data

    Returns:
        Created ContentSource instance

    Raises:
        HTTPException: 404 if episode not found
    """
    # Verify episode exists (RLS ensures it's in correct tenant)
    episode = await db.get(Episode, content_data.episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found"
        )

    content_source = ContentSource(
        episode_id=content_data.episode_id,
        tenant_id=tenant_id,
        source_type=content_data.source_type,
        source_data=content_data.source_data,
        extraction_status="pending",  # Initial status
        extracted_content=None,
        error_message=None
    )
    db.add(content_source)
    await db.commit()
    return content_source


async def _upload_pdf_to_s3(file_path: str, s3_key: str) -> str:
    """
    Upload a PDF to S3 and return its URL.

    Kept at module scope so tests can patch it. Raises 503 when S3 is not
    configured, since a PDF that is not stored cannot later be extracted.

    Args:
        file_path: Local temp file path to upload.
        s3_key: Destination S3 object key.

    Returns:
        S3 URL string.

    Raises:
        HTTPException: 503 if S3 storage is not configured.
    """
    from ..config import settings
    from ..services.storage_service import StorageService

    bucket = getattr(settings, "AWS_S3_BUCKET", None)
    if not bucket:
        # Without S3 the PDF cannot be persisted anywhere extraction can read it,
        # so reject the upload rather than recording an unretrievable s3_key.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured; PDF uploads are unavailable.",
        )

    storage = StorageService(bucket_name=bucket, region_name=settings.AWS_REGION)
    return await storage.upload_file(
        file_path=file_path,
        s3_key=s3_key,
        content_type="application/pdf",
        public=False,
    )


async def upload_pdf_content(
    db: AsyncSession,
    tenant_id: UUID,
    episode_id: UUID,
    file: UploadFile,
    description: Optional[str] = None,
) -> ContentSource:
    """
    Upload a PDF file to S3 and create a 'pdf' content source for an episode.

    Validates the episode exists, the file is a PDF, and the size is within
    limits, then stores the file in S3 under
    ``content/{tenant_id}/{episode_id}/{uuid}_{filename}`` and records a
    ContentSource with ``source_data={s3_key, filename, mime_type}`` and an
    initial ``extraction_status='pending'``.

    Args:
        db: Database session.
        tenant_id: Tenant ID for isolation.
        episode_id: Episode the PDF belongs to.
        file: Uploaded PDF file.
        description: Optional description (currently unused metadata).

    Returns:
        Created ContentSource instance.

    Raises:
        HTTPException: 404 if episode not found, 413 if too large,
            422 if invalid format / storage failure.
    """
    # Verify episode exists (RLS ensures it's in the correct tenant)
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found",
        )

    # Validate PDF format before reading the whole file
    filename = file.filename or ""
    try:
        validate_pdf_format(filename, file.content_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Read contents and enforce size limits
    file_bytes = await file.read()
    file_size = len(file_bytes)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded PDF is empty",
        )
    if file_size > MAX_PDF_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large ({file_size} bytes). "
                f"Maximum allowed size is {MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB"
            ),
        )

    # Verify the bytes are actually a PDF (magic header) so non-PDF content is
    # rejected synchronously with 422 rather than failing later during extraction.
    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is not a valid PDF (missing %PDF- header).",
        )

    # Build a tenant/episode-scoped S3 key with a sanitized filename
    safe_name = sanitize_filename(filename) or "document.pdf"
    s3_key = f"content/{tenant_id}/{episode_id}/{uuid.uuid4()}_{safe_name}"

    # Write to a temp file and upload to S3, cleaning up afterwards
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        await _upload_pdf_to_s3(temp_path, s3_key)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to store PDF: {str(e)}",
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    content_source = ContentSource(
        episode_id=episode_id,
        tenant_id=tenant_id,
        source_type="pdf",
        source_data={
            "s3_key": s3_key,
            "filename": filename,
            "mime_type": "application/pdf",
        },
        extraction_status="pending",
        extracted_content=None,
        error_message=None,
    )
    db.add(content_source)
    await db.commit()
    return content_source


async def get_content_sources(
    db: AsyncSession,
    episode_id: UUID,
    skip: int = 0,
    limit: int = 20
) -> tuple[list[ContentSource], int]:
    """
    Get paginated list of content sources for an episode.

    RLS automatically filters by tenant.
    Results ordered by created_at ascending.

    Args:
        db: Database session
        episode_id: Episode ID to filter by
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return

    Returns:
        Tuple of (content sources list, total count)
    """
    # Build query filtered by episode_id
    query = select(ContentSource).where(ContentSource.episode_id == episode_id)

    # Get total count (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated results, ordered by created_at
    query = query.offset(skip).limit(limit).order_by(
        ContentSource.created_at.asc()
    )
    result = await db.execute(query)
    content_sources = result.scalars().all()

    return list(content_sources), total


async def get_content_source_by_id(
    db: AsyncSession,
    content_id: UUID
) -> Optional[ContentSource]:
    """
    Get content source by ID.

    RLS ensures user can only access content sources within their tenant.
    Returns None if content source doesn't exist or belongs to different tenant.

    Args:
        db: Database session
        content_id: UUID of content source to retrieve

    Returns:
        ContentSource instance or None if not found
    """
    result = await db.execute(
        select(ContentSource).where(ContentSource.id == content_id)
    )
    return result.scalar_one_or_none()


async def update_content_source(
    db: AsyncSession,
    content_source: ContentSource,
    update_data: ContentSourceUpdate
) -> ContentSource:
    """
    Update content source with partial data.

    Only updates fields provided in update_data (partial updates supported).
    Uses Pydantic's model_dump(exclude_unset=True) to only update provided fields.

    Args:
        db: Database session
        content_source: Existing content source instance
        update_data: Update data (only provided fields will be updated)

    Returns:
        Updated ContentSource instance
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(content_source, field, value)

    await db.commit()
    return content_source


async def delete_content_source(
    db: AsyncSession,
    content_source: ContentSource
) -> None:
    """
    Hard delete content source.

    Content sources use hard delete (no soft delete).

    Args:
        db: Database session
        content_source: ContentSource instance to delete
    """
    await db.delete(content_source)
    await db.commit()
