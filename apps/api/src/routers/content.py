"""
Content source router for RESTful API endpoints.

Provides CRUD operations for content sources with pagination, episode filtering,
and extraction status management. All endpoints require authentication and
automatically enforce tenant isolation via RLS.

Note: Content sources are nested under episodes at /episodes/{episode_id}/content
"""

import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, status, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, Optional

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User, Episode
from ..schemas.content import (
    ContentSourceCreate,
    ContentSourceUpdate,
    ContentSourceResponse,
    ContentSourceListResponse
)
from ..services.content_service import (
    add_content_source,
    upload_pdf_content,
    get_content_sources,
    get_content_source_by_id,
    update_content_source,
    delete_content_source
)
from ..services.source_validator_service import (
    SourceValidatorService,
    URLValidationError,
    TextValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["content"])


@router.post(
    "/episodes/{episode_id}/content",
    response_model=ContentSourceResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_content_source(
    episode_id: UUID,
    content_data: ContentSourceCreate,
    auto_extract: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new content source for episode.

    Validates episode exists and belongs to user's tenant.
    Validates source_data structure based on source_type.
    Requires authentication. Initial extraction_status is 'pending'.

    If auto_extract=True (default), queues a background extraction task
    immediately after creation so content is ready for generation.

    Args:
        episode_id: UUID of parent episode
        content_data: Content source creation data with source_type and source_data
        auto_extract: Whether to automatically trigger extraction (default True)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Created content source with all fields

    Raises:
        HTTPException: 404 if episode not found
        HTTPException: 422 if source_data validation fails
    """
    # Verify episode_id in path matches episode_id in body
    if content_data.episode_id != episode_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode ID in path must match episode_id in request body"
        )

    # Verify episode exists and user has access
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found"
        )

    # Validate source data semantics (GAP-015)
    validator = SourceValidatorService()
    try:
        await validator.validate_by_type(
            source_type=content_data.source_type,
            source_data=content_data.source_data,
        )
    except (URLValidationError, TextValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )

    content_source = await add_content_source(
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        content_data=content_data
    )

    # Auto-trigger extraction if requested
    if auto_extract and content_source.source_type in ('url', 'pdf', 'text'):
        try:
            from ..tasks.content_extraction import extract_content_task
            extract_content_task.delay(
                content_source_id=str(content_source.id),
                source_type=content_source.source_type,
            )
            logger.info(
                f"Triggered extraction task for content source {content_source.id}"
            )
        except Exception as e:
            # Broker unavailable — log but don't fail creation
            logger.warning(
                f"Could not queue extraction task for {content_source.id}: {e}"
            )

    return content_source


@router.post(
    "/episodes/{episode_id}/content/upload",
    response_model=ContentSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pdf_content_source(
    episode_id: UUID,
    file: UploadFile = File(..., description="PDF file (application/pdf, max 50MB)"),
    description: Optional[str] = Form(None, max_length=500, description="Optional description"),
    auto_extract: bool = Form(True, description="Trigger extraction immediately after upload"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF file as a content source for an episode.

    Accepts multipart/form-data with a PDF file plus optional metadata. Stores
    the file in S3, creates a 'pdf' content source recording its ``s3_key`` and
    ``filename``, and (when ``auto_extract`` is true) queues a background
    extraction task so the content is ready for generation.

    Args:
        episode_id: UUID of the parent episode.
        file: Uploaded PDF file.
        description: Optional description.
        auto_extract: Whether to automatically trigger extraction (default True).
        current_user: Authenticated user (from JWT token).
        db: Database session.

    Returns:
        Created content source with all fields.

    Raises:
        HTTPException: 404 if episode not found, 413 if file too large,
            422 if the file is not a valid PDF.
    """
    content_source = await upload_pdf_content(
        db=db,
        tenant_id=current_user.tenant_id,
        episode_id=episode_id,
        file=file,
        description=description,
    )

    # Auto-trigger extraction if requested (mirrors create_content_source)
    if auto_extract:
        try:
            from ..tasks.content_extraction import extract_content_task
            extract_content_task.delay(
                content_source_id=str(content_source.id),
                source_type=content_source.source_type,
            )
            logger.info(
                f"Triggered extraction task for uploaded PDF content source {content_source.id}"
            )
        except Exception as e:
            # Broker unavailable — log but don't fail the upload
            logger.warning(
                f"Could not queue extraction task for {content_source.id}: {e}"
            )

    return content_source


@router.get(
    "/episodes/{episode_id}/content",
    response_model=ContentSourceListResponse
)
async def list_content_sources(
    episode_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List content sources for an episode with pagination.

    Automatically filtered by user's tenant via RLS.
    Results ordered by created_at ascending.
    Validates episode ownership before listing.

    Args:
        episode_id: UUID of parent episode
        page: Page number (1-indexed)
        page_size: Items per page (1-100)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Paginated list of content sources with metadata

    Raises:
        HTTPException: 404 if episode not found or different tenant
    """
    # Verify episode exists and user has access
    episode = await db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode not found"
        )

    skip = (page - 1) * page_size
    content_sources, total = await get_content_sources(
        db=db,
        episode_id=episode_id,
        skip=skip,
        limit=page_size
    )

    total_pages = (total + page_size - 1) // page_size  # Ceiling division

    return ContentSourceListResponse(
        content_sources=content_sources,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/content/{content_id}", response_model=ContentSourceResponse)
async def get_content_source(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get content source details by ID.

    Returns 404 if content source doesn't exist or belongs to different tenant.
    RLS automatically ensures tenant isolation.

    Args:
        content_id: UUID of content source to retrieve
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Content source details with all fields

    Raises:
        HTTPException: 404 if content source not found or different tenant
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    return content_source


@router.put("/content/{content_id}", response_model=ContentSourceResponse)
async def update_content_source_endpoint(
    content_id: UUID,
    update_data: ContentSourceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update content source with partial data.

    Only provided fields are updated (partial updates supported).
    Returns 404 if content source not found or belongs to different tenant.

    Args:
        content_id: UUID of content source to update
        update_data: Update data (only provided fields will be updated)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Updated content source with all fields

    Raises:
        HTTPException: 404 if content source not found or different tenant
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    updated_content_source = await update_content_source(
        db=db,
        content_source=content_source,
        update_data=update_data
    )

    return updated_content_source


@router.delete("/content/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_source_endpoint(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete content source (hard delete).

    Permanently removes content source.
    Returns 404 if content source not found or belongs to different tenant.

    Args:
        content_id: UUID of content source to delete
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if content source not found or different tenant
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    await delete_content_source(db=db, content_source=content_source)
    return None  # 204 No Content


@router.post(
    "/content/{content_id}/extract",
    status_code=status.HTTP_202_ACCEPTED
)
async def trigger_content_extraction(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Trigger content extraction for a content source.

    Queues a background Celery task to extract content from the source URL,
    PDF file, or text data. Returns immediately with task information.

    The extraction updates ContentSource.extraction_status and
    ContentSource.extracted_content asynchronously. Poll
    GET /content/{content_id}/extraction-status to check progress.

    Args:
        content_id: UUID of content source to extract
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        202 Accepted with task_id, content_source_id, and status

    Raises:
        HTTPException: 404 if content source not found
        HTTPException: 422 if source_type is not extractable
        HTTPException: 503 if extraction task cannot be queued
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    if content_source.source_type not in ('url', 'pdf', 'text'):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Source type '{content_source.source_type}' does not support extraction. "
                "Supported types: url, pdf, text"
            )
        )

    try:
        from ..tasks.content_extraction import extract_content_task
        task = extract_content_task.delay(
            content_source_id=str(content_id),
            source_type=content_source.source_type,
        )
        logger.info(
            f"Triggered extraction task {task.id} for content source {content_id}"
        )
    except Exception as e:
        logger.error(f"Failed to queue extraction task for {content_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Extraction service unavailable — please try again later"
        )

    return {
        "content_source_id": str(content_id),
        "task_id": task.id,
        "status": "extracting",
        "message": "Content extraction started",
    }


@router.get("/content/{content_id}/extraction-status")
async def get_extraction_status(
    content_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get current extraction status for a content source.

    Returns the extraction_status, word count (if complete), and error details
    (if failed). Useful for polling from the frontend to show progress.

    Args:
        content_id: UUID of content source to check
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Dictionary with extraction_status, extracted_word_count, error_message

    Raises:
        HTTPException: 404 if content source not found
    """
    content_source = await get_content_source_by_id(db=db, content_id=content_id)

    if content_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content source not found"
        )

    word_count = None
    if content_source.extracted_content:
        word_count = len(content_source.extracted_content.split())

    return {
        "content_source_id": str(content_id),
        "extraction_status": content_source.extraction_status,
        "extracted_word_count": word_count,
        "error_message": content_source.error_message,
        "updated_at": content_source.updated_at.isoformat() if content_source.updated_at else None,
    }
