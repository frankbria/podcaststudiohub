"""
TTS configuration router for RESTful API endpoints.

Provides CRUD operations for TTS configurations with pagination, validation,
and default configuration management. All endpoints require authentication and
automatically enforce tenant isolation via RLS.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.tts_configuration import (
	TTSConfigCreate,
	TTSConfigUpdate,
	TTSConfigResponse,
	TTSConfigListResponse,
)
from ..services.tts_configuration_service import (
	create_tts_configuration,
	get_tts_configurations,
	get_tts_configuration_by_id,
	update_tts_configuration,
	delete_tts_configuration,
	set_default_tts_configuration,
)

router = APIRouter(prefix="/tts-configs", tags=["tts-configurations"])


@router.post("", response_model=TTSConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_tts_config_endpoint(
	config_data: TTSConfigCreate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Create new TTS configuration.

	Requires authentication. Configuration automatically assigned to user's tenant.
	RLS ensures tenant isolation automatically.

	Args:
		config_data: Configuration creation data with name, provider, and config
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Created configuration with all fields
	"""
	tts_config = await create_tts_configuration(
		db=db,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
		config_data=config_data,
	)
	return tts_config


@router.get("", response_model=TTSConfigListResponse)
async def list_tts_configs(
	page: int = Query(1, ge=1, description="Page number (1-indexed)"),
	page_size: int = Query(20, ge=1, le=100, description="Items per page"),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	List TTS configurations with pagination.

	Automatically filtered by user's tenant via RLS.

	Args:
		page: Page number (1-indexed)
		page_size: Items per page (1-100)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Paginated list of configurations with metadata
	"""
	skip = (page - 1) * page_size
	configs, total = await get_tts_configurations(
		db=db,
		skip=skip,
		limit=page_size,
	)

	total_pages = (total + page_size - 1) // page_size if total > 0 else 0

	return TTSConfigListResponse(
		configs=configs,
		total=total,
		page=page,
		page_size=page_size,
		total_pages=total_pages,
	)


@router.get("/{config_id}", response_model=TTSConfigResponse)
async def get_tts_config(
	config_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Get TTS configuration details by ID.

	Returns 404 if configuration doesn't exist or belongs to different tenant.
	RLS automatically ensures tenant isolation.

	Args:
		config_id: UUID of configuration to retrieve
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Configuration details with all fields

	Raises:
		HTTPException: 404 if configuration not found or different tenant
	"""
	tts_config = await get_tts_configuration_by_id(db=db, config_id=config_id)

	if tts_config is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="TTS configuration not found",
		)

	return tts_config


@router.put("/{config_id}", response_model=TTSConfigResponse)
async def update_tts_config_endpoint(
	config_id: UUID,
	update_data: TTSConfigUpdate,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Update TTS configuration with partial data.

	Only provided fields are updated (partial updates supported).
	Returns 404 if configuration not found or belongs to different tenant.

	Args:
		config_id: UUID of configuration to update
		update_data: Update data (only provided fields will be updated)
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated configuration with all fields

	Raises:
		HTTPException: 404 if configuration not found or different tenant
	"""
	tts_config = await get_tts_configuration_by_id(db=db, config_id=config_id)

	if tts_config is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="TTS configuration not found",
		)

	updated_config = await update_tts_configuration(
		db=db,
		tts_config=tts_config,
		update_data=update_data,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
	)

	return updated_config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tts_config_endpoint(
	config_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Delete a TTS configuration.

	Returns 404 if configuration not found or belongs to different tenant.

	Args:
		config_id: UUID of configuration to delete
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		None (204 No Content)

	Raises:
		HTTPException: 404 if configuration not found or different tenant
	"""
	tts_config = await get_tts_configuration_by_id(db=db, config_id=config_id)

	if tts_config is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="TTS configuration not found",
		)

	await delete_tts_configuration(db=db, tts_config=tts_config)
	return None


@router.post("/{config_id}/set-default", response_model=TTSConfigResponse)
async def set_default_tts_config_endpoint(
	config_id: UUID,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db),
):
	"""
	Set a TTS configuration as the default for the current user's tenant.

	Clears the default flag from all other configurations for this user.
	Returns 404 if configuration not found or belongs to different tenant.

	Args:
		config_id: UUID of configuration to set as default
		current_user: Authenticated user (from JWT token)
		db: Database session

	Returns:
		Updated configuration with is_default=True

	Raises:
		HTTPException: 404 if configuration not found or different tenant
	"""
	tts_config = await get_tts_configuration_by_id(db=db, config_id=config_id)

	if tts_config is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="TTS configuration not found",
		)

	updated_config = await set_default_tts_configuration(
		db=db,
		tts_config=tts_config,
		user_id=current_user.id,
		tenant_id=current_user.tenant_id,
	)

	return updated_config
