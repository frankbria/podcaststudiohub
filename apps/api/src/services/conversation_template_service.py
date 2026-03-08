"""
Conversation template service layer for business logic.

Provides CRUD operations for conversation templates with pagination,
default management, and referential integrity checks. RLS ensures
tenant isolation automatically.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from uuid import UUID
from typing import Optional

from ..models import ConversationTemplate, Episode
from ..models.project import Project
from ..schemas.conversation_template import ConversationTemplateCreate, ConversationTemplateUpdate


async def create_conversation_template(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	template_data: ConversationTemplateCreate
) -> ConversationTemplate:
	"""
	Create a new conversation template for a user.

	If is_default=True, clears the default flag from all other templates
	for this user in the same transaction.

	Args:
		db: Database session
		user_id: ID of user creating the template
		tenant_id: Tenant ID for isolation
		template_data: Template creation data

	Returns:
		Created ConversationTemplate instance
	"""
	if template_data.is_default:
		await _clear_default_flag(db, user_id, tenant_id)

	template = ConversationTemplate(
		name=template_data.name,
		description=template_data.description,
		config=template_data.config.model_dump(exclude_none=False),
		is_default=template_data.is_default,
		user_id=user_id,
		tenant_id=tenant_id,
	)
	db.add(template)
	await db.commit()
	return template


async def get_conversation_templates(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 20,
) -> tuple[list[ConversationTemplate], int]:
	"""
	Get paginated list of conversation templates.

	RLS automatically filters by tenant based on the session's tenant_id.

	Args:
		db: Database session
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return

	Returns:
		Tuple of (templates list, total count)
	"""
	query = select(ConversationTemplate)

	# Get total count
	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	# Get paginated results, ordered by most recent first
	query = query.offset(skip).limit(limit).order_by(ConversationTemplate.created_at.desc())
	result = await db.execute(query)
	templates = result.scalars().all()

	return list(templates), total


async def get_conversation_template_by_id(
	db: AsyncSession,
	template_id: UUID
) -> Optional[ConversationTemplate]:
	"""
	Get conversation template by ID.

	RLS ensures user can only access templates within their tenant.
	Returns None if template doesn't exist or belongs to different tenant.

	Args:
		db: Database session
		template_id: UUID of template to retrieve

	Returns:
		ConversationTemplate instance or None if not found
	"""
	result = await db.execute(
		select(ConversationTemplate).where(ConversationTemplate.id == template_id)
	)
	return result.scalar_one_or_none()


async def update_conversation_template(
	db: AsyncSession,
	template: ConversationTemplate,
	update_data: ConversationTemplateUpdate,
	user_id: UUID,
	tenant_id: UUID,
) -> ConversationTemplate:
	"""
	Update conversation template with partial data.

	Only updates fields provided in update_data (partial updates supported).
	If is_default=True, clears the default flag from all other templates.

	Args:
		db: Database session
		template: Existing template instance
		update_data: Update data (only provided fields will be updated)
		user_id: User ID (for default management)
		tenant_id: Tenant ID (for default management)

	Returns:
		Updated ConversationTemplate instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)

	if update_dict.get('is_default') is True:
		await _clear_default_flag(db, user_id, tenant_id, exclude_id=template.id)

	for field, value in update_dict.items():
		if field == 'config' and value is not None:
			# Convert Pydantic model to dict if needed
			if hasattr(value, 'model_dump'):
				value = value.model_dump(exclude_none=False)
		setattr(template, field, value)

	await db.commit()
	return template


async def delete_conversation_template(
	db: AsyncSession,
	template: ConversationTemplate,
) -> None:
	"""
	Delete a conversation template.

	Args:
		db: Database session
		template: Template instance to delete
	"""
	await db.delete(template)
	await db.commit()


async def check_template_in_use(
	db: AsyncSession,
	template_id: UUID,
) -> Optional[str]:
	"""
	Check if a template is referenced by episodes or projects.

	Args:
		db: Database session
		template_id: UUID of template to check

	Returns:
		Error message string if in use, None if safe to delete
	"""
	# Check episodes referencing this template
	episode_count_result = await db.execute(
		select(func.count()).where(
			Episode.template_id == template_id
		)
	)
	episode_count = episode_count_result.scalar() or 0

	if episode_count > 0:
		return f"Cannot delete template: {episode_count} episode(s) currently use this template"

	# Check projects with this as default template
	project_count_result = await db.execute(
		select(func.count()).where(
			Project.default_template_id == template_id
		)
	)
	project_count = project_count_result.scalar() or 0

	if project_count > 0:
		return f"Cannot delete template: {project_count} project(s) use this as their default template"

	return None


async def set_default_conversation_template(
	db: AsyncSession,
	template: ConversationTemplate,
	user_id: UUID,
	tenant_id: UUID,
) -> ConversationTemplate:
	"""
	Set a template as the default, clearing default from all others.

	Uses a transaction to atomically clear all existing defaults and
	set the new one.

	Args:
		db: Database session
		template: Template to set as default
		user_id: User ID for filtering
		tenant_id: Tenant ID for filtering

	Returns:
		Updated ConversationTemplate instance
	"""
	await _clear_default_flag(db, user_id, tenant_id, exclude_id=template.id)
	template.is_default = True
	await db.commit()
	return template


async def _clear_default_flag(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	exclude_id: Optional[UUID] = None,
) -> None:
	"""
	Clear is_default flag from all templates for user/tenant.

	Args:
		db: Database session
		user_id: User ID for filtering
		tenant_id: Tenant ID for filtering
		exclude_id: Optional template ID to exclude from clearing
	"""
	stmt = (
		update(ConversationTemplate)
		.where(
			ConversationTemplate.user_id == user_id,
			ConversationTemplate.tenant_id == tenant_id,
			ConversationTemplate.is_default,
		)
		.values(is_default=False)
	)
	if exclude_id is not None:
		stmt = stmt.where(ConversationTemplate.id != exclude_id)

	await db.execute(stmt)
