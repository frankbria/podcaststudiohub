"""
TTS Configuration service layer for business logic.

Provides CRUD operations for TTS configurations with pagination,
validation, and default flag management. RLS ensures tenant isolation.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from uuid import UUID
from typing import Optional

from ..models import TTSConfiguration
from ..schemas.tts_config import TTSConfigurationCreate, TTSConfigurationUpdate


async def create_tts_configuration(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	config_data: TTSConfigurationCreate
) -> TTSConfiguration:
	"""
	Create new TTS configuration for user.

	If is_default is True, clears the default flag from all other
	configurations for this user in the same tenant first.

	Args:
		db: Database session
		user_id: ID of user creating the configuration
		tenant_id: Tenant ID for isolation
		config_data: TTS configuration creation data

	Returns:
		Created TTSConfiguration instance
	"""
	if config_data.is_default:
		await _clear_default_for_user(db, user_id, tenant_id)

	tts_config = TTSConfiguration(
		name=config_data.name,
		provider=config_data.provider,
		config=config_data.config,
		is_default=config_data.is_default,
		user_id=user_id,
		tenant_id=tenant_id,
	)
	db.add(tts_config)
	await db.commit()
	return tts_config


async def get_tts_configurations(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 20
) -> tuple[list[TTSConfiguration], int]:
	"""
	Get paginated list of TTS configurations.

	RLS automatically filters by tenant based on the session's tenant_id.

	Args:
		db: Database session
		skip: Number of records to skip (for pagination)
		limit: Maximum number of records to return

	Returns:
		Tuple of (configurations list, total count)
	"""
	query = select(TTSConfiguration)

	count_query = select(func.count()).select_from(query.subquery())
	total_result = await db.execute(count_query)
	total = total_result.scalar()

	query = query.offset(skip).limit(limit).order_by(TTSConfiguration.created_at.desc())
	result = await db.execute(query)
	configs = result.scalars().all()

	return list(configs), total


async def get_tts_configuration_by_id(
	db: AsyncSession,
	config_id: UUID
) -> Optional[TTSConfiguration]:
	"""
	Get TTS configuration by ID.

	RLS ensures user can only access configurations within their tenant.
	Returns None if configuration doesn't exist or belongs to different tenant.

	Args:
		db: Database session
		config_id: UUID of configuration to retrieve

	Returns:
		TTSConfiguration instance or None if not found
	"""
	result = await db.execute(
		select(TTSConfiguration).where(TTSConfiguration.id == config_id)
	)
	return result.scalar_one_or_none()


async def update_tts_configuration(
	db: AsyncSession,
	tts_config: TTSConfiguration,
	update_data: TTSConfigurationUpdate
) -> TTSConfiguration:
	"""
	Update TTS configuration with partial data.

	Only updates fields provided in update_data (partial updates supported).
	If is_default is set to True, clears default from all other configurations
	for the same user in the same tenant.

	Args:
		db: Database session
		tts_config: Existing TTSConfiguration instance
		update_data: Update data (only provided fields will be updated)

	Returns:
		Updated TTSConfiguration instance
	"""
	update_dict = update_data.model_dump(exclude_unset=True)

	if update_dict.get("is_default") is True:
		await _clear_default_for_user(db, tts_config.user_id, tts_config.tenant_id, exclude_id=tts_config.id)

	for field, value in update_dict.items():
		setattr(tts_config, field, value)

	await db.commit()
	return tts_config


async def delete_tts_configuration(
	db: AsyncSession,
	tts_config: TTSConfiguration
) -> None:
	"""
	Hard delete a TTS configuration.

	Args:
		db: Database session
		tts_config: TTSConfiguration instance to delete
	"""
	await db.delete(tts_config)
	await db.commit()


async def set_default_tts_configuration(
	db: AsyncSession,
	tts_config: TTSConfiguration
) -> TTSConfiguration:
	"""
	Set a TTS configuration as the default for the user's tenant.

	Clears is_default from all other configurations for this user
	in the same tenant, then sets is_default=True on the given config.

	Args:
		db: Database session
		tts_config: TTSConfiguration instance to set as default

	Returns:
		Updated TTSConfiguration instance
	"""
	await _clear_default_for_user(db, tts_config.user_id, tts_config.tenant_id, exclude_id=tts_config.id)
	tts_config.is_default = True
	await db.commit()
	return tts_config


async def _clear_default_for_user(
	db: AsyncSession,
	user_id: UUID,
	tenant_id: UUID,
	exclude_id: Optional[UUID] = None
) -> None:
	"""
	Clear is_default flag from all TTS configurations for a user in a tenant.

	Args:
		db: Database session
		user_id: User ID
		tenant_id: Tenant ID
		exclude_id: Optional configuration ID to exclude from clearing
	"""
	stmt = (
		update(TTSConfiguration)
		.where(
			TTSConfiguration.user_id == user_id,
			TTSConfiguration.tenant_id == tenant_id,
			TTSConfiguration.is_default.is_(True),
		)
		.values(is_default=False)
	)
	if exclude_id is not None:
		stmt = stmt.where(TTSConfiguration.id != exclude_id)
	await db.execute(stmt)
