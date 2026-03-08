"""
Audio snippet router for RESTful API endpoints.

Provides CRUD operations and file upload for audio snippets (intros, outros,
background music, ads). All endpoints require authentication and enforce
tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.audio_snippet import (
	AudioSnippetUpdate,
	AudioSnippetResponse,
	AudioSnippetListResponse,
	DownloadUrlResponse,
	SnippetType,
)
from ..services.audio_snippet_service import (
	upload_audio_snippet,
	get_audio_snippets,
	get_audio_snippet_by_id,
	update_audio_snippet,
	delete_audio_snippet,
	generate_download_url,
)

router = APIRouter(prefix="/audio-snippets", tags=["audio-snippets"])


@router.post(
	"/upload",
	response_model=AudioSnippetResponse,
	status_code=status.HTTP_201_CREATED,
)
async def upload_audio_snippet_endpoint(
	file: UploadFile = File(..., description="Audio file (MP3, WAV, AAC, OGG, max 50MB)"),
	name: str = Form(..., max_length=255, description="Snippet name"),
	snippet_type: SnippetType = Form(..., description="Type of snippet"),
	description: Optional[str] = Form(None, max_length=500, description="Optional description"),
	project_id: Optional[UUID] = Form(None, description="Optional project scope"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Upload an audio file and create a new snippet record.

	Accepts multipart/form-data with audio file plus metadata.
	Validates file format (MP3, WAV, AAC, OGG) and size (100KB–50MB).
	Extracts audio duration automatically and uploads to S3.

	Args:
		file: Audio file (MP3, WAV, AAC, OGG)
		name: Snippet name (required)
		snippet_type: Type of snippet: intro, outro, midroll, ad, music, other
		description: Optional description
		project_id: Optional project scope UUID
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created audio snippet with S3 URL and metadata

	Raises:
		HTTPException: 413 if file too large, 422 if invalid format
	"""
	snippet = await upload_audio_snippet(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		file=file,
		name=name,
		snippet_type=snippet_type.value,
		description=description,
		project_id=project_id,
	)
	return snippet


@router.get("", response_model=AudioSnippetListResponse)
async def list_audio_snippets(
	type: Optional[str] = Query(None, description="Filter by snippet type"),
	project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
	search: Optional[str] = Query(None, description="Search by name"),
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	List audio snippets with optional filtering and pagination.

	Automatically filtered by user's tenant via RLS.
	Results ordered by creation date descending.

	Args:
		type: Optional snippet type filter (intro, outro, midroll, ad, music, other)
		project_id: Optional project ID to filter by
		search: Optional name search term
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of audio snippets with metadata
	"""
	skip = (page - 1) * page_size
	snippets, total = await get_audio_snippets(
		db=db,
		snippet_type=type,
		project_id=project_id,
		search=search,
		skip=skip,
		limit=page_size,
	)

	total_pages = (total + page_size - 1) // page_size if total > 0 else 1

	return AudioSnippetListResponse(
		snippets=snippets,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages,
	)


@router.get("/{snippet_id}", response_model=AudioSnippetResponse)
async def get_audio_snippet(
	snippet_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get audio snippet details by ID.

	Returns 404 if snippet doesn't exist or belongs to different tenant.

	Args:
		snippet_id: UUID of snippet to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Audio snippet details with all fields

	Raises:
		HTTPException: 404 if snippet not found or different tenant
	"""
	snippet = await get_audio_snippet_by_id(db=db, snippet_id=snippet_id)

	if snippet is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Audio snippet not found"
		)

	return snippet


@router.put("/{snippet_id}", response_model=AudioSnippetResponse)
async def update_audio_snippet_endpoint(
	snippet_id: UUID,
	update_data: AudioSnippetUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Update audio snippet metadata.

	Only name, description, and snippet_type can be updated.
	To replace the audio file, delete the snippet and upload a new one.

	Args:
		snippet_id: UUID of snippet to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated audio snippet with all fields

	Raises:
		HTTPException: 404 if snippet not found or different tenant
	"""
	snippet = await get_audio_snippet_by_id(db=db, snippet_id=snippet_id)

	if snippet is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Audio snippet not found"
		)

	updated_snippet = await update_audio_snippet(
		db=db,
		snippet=snippet,
		update_data=update_data,
	)

	return updated_snippet


@router.delete("/{snippet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audio_snippet_endpoint(
	snippet_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Delete audio snippet from S3 and database.

	Removes the file from S3 storage and deletes the database record.
	Returns 404 if snippet not found or belongs to different tenant.

	Args:
		snippet_id: UUID of snippet to delete
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if snippet not found or different tenant
	"""
	snippet = await get_audio_snippet_by_id(db=db, snippet_id=snippet_id)

	if snippet is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Audio snippet not found"
		)

	await delete_audio_snippet(db=db, snippet=snippet)
	return None


@router.get("/{snippet_id}/download", response_model=DownloadUrlResponse)
async def get_download_url(
	snippet_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get a presigned download URL for an audio snippet.

	Returns a time-limited presigned S3 URL valid for 1 hour.
	Requires the snippet to have an S3 key stored.

	Args:
		snippet_id: UUID of snippet
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Presigned download URL with expiration info

	Raises:
		HTTPException: 404 if snippet not found, 503 if S3 not configured
	"""
	snippet = await get_audio_snippet_by_id(db=db, snippet_id=snippet_id)

	if snippet is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Audio snippet not found"
		)

	download_url = await generate_download_url(snippet=snippet)

	return DownloadUrlResponse(
		snippet_id=snippet.id,
		download_url=download_url,
		expires_in_seconds=3600,
	)
