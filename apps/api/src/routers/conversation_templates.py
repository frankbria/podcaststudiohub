"""
Conversation template router for RESTful API endpoints.

Provides CRUD operations for conversation templates with pagination, validation,
and default template management. All endpoints require authentication and
automatically enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.conversation_template import (
	ConversationTemplateCreate,
	ConversationTemplateUpdate,
	ConversationTemplateResponse,
	ConversationTemplateListResponse,
)
from ..services.conversation_template_service import (
	create_conversation_template,
	get_conversation_templates,
	get_conversation_template_by_id,
	update_conversation_template,
	delete_conversation_template,
	check_template_in_use,
	set_default_conversation_template,
)

router = APIRouter(prefix="/conversation-templates", tags=["conversation-templates"])


@router.post("", response_model=ConversationTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template_endpoint(
	template_data: ConversationTemplateCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Create new conversation template.

	Requires authentication. Template automatically assigned to user's tenant.
	RLS ensures tenant isolation automatically.

	Args:
		template_data: Template creation data with name, description, and config
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created template with all fields
	"""
	template = await create_conversation_template(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		template_data=template_data
	)
	return template


@router.get("", response_model=ConversationTemplateListResponse)
async def list_templates(
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	List conversation templates with pagination.

	Automatically filtered by user's tenant via RLS.

	Args:
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of templates with metadata
	"""
	skip = (page - 1) * page_size
	templates, total = await get_conversation_templates(
		db=db,
		skip=skip,
		limit=page_size,
	)

	total_pages = (total + page_size - 1) // page_size if total > 0 else 0

	return ConversationTemplateListResponse(
		templates=templates,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages
	)


@router.get("/{template_id}", response_model=ConversationTemplateResponse)
async def get_template(
	template_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Get conversation template details by ID.

	Returns 404 if template doesn't exist or belongs to different tenant.
	RLS automatically ensures tenant isolation.

	Args:
		template_id: UUID of template to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Template details with all fields

	Raises:
		HTTPException: 404 if template not found or different tenant
	"""
	template = await get_conversation_template_by_id(db=db, template_id=template_id)

	if template is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Conversation template not found"
		)

	return template


@router.put("/{template_id}", response_model=ConversationTemplateResponse)
async def update_template_endpoint(
	template_id: UUID,
	update_data: ConversationTemplateUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Update conversation template with partial data.

	Only provided fields are updated (partial updates supported).
	Returns 404 if template not found or belongs to different tenant.

	Args:
		template_id: UUID of template to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated template with all fields

	Raises:
		HTTPException: 404 if template not found or different tenant
	"""
	template = await get_conversation_template_by_id(db=db, template_id=template_id)

	if template is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Conversation template not found"
		)

	updated_template = await update_conversation_template(
		db=db,
		template=template,
		update_data=update_data,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
	)

	return updated_template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template_endpoint(
	template_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Delete a conversation template.

	Returns 404 if template not found or belongs to different tenant.
	Returns 409 Conflict if template is currently in use by episodes or projects.

	Args:
		template_id: UUID of template to delete
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if template not found or different tenant
		HTTPException: 409 if template is in use
	"""
	template = await get_conversation_template_by_id(db=db, template_id=template_id)

	if template is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Conversation template not found"
		)

	error_message = await check_template_in_use(db=db, template_id=template_id)
	if error_message:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=error_message
		)

	await delete_conversation_template(db=db, template=template)
	return None


@router.post("/{template_id}/set-default", response_model=ConversationTemplateResponse)
async def set_default_endpoint(
	template_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""
	Set a template as the default for the current user's tenant.

	Clears the default flag from all other templates for this user.
	Returns 404 if template not found or belongs to different tenant.

	Args:
		template_id: UUID of template to set as default
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated template with is_default=True

	Raises:
		HTTPException: 404 if template not found or different tenant
	"""
	template = await get_conversation_template_by_id(db=db, template_id=template_id)

	if template is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Conversation template not found"
		)

	updated_template = await set_default_conversation_template(
		db=db,
		template=template,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
	)

	return updated_template
