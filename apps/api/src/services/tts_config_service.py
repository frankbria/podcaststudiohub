"""
Service layer for TTS configuration CRUD operations.

Provides async functions for creating, reading, updating, and deleting
TTS configurations with tenant isolation.
"""

import logging
from typing import Optional, Tuple, List
from uuid import UUID
from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tts_configuration import TTSConfiguration
from ..schemas.tts_config import TTSConfigCreate, TTSConfigUpdate

logger = logging.getLogger(__name__)


async def create_tts_config(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    config_data: TTSConfigCreate,
) -> TTSConfiguration:
    """
    Create a new TTS configuration.

    If is_default=True, clears the default flag on all other configs
    for this user before setting the new one.

    Args:
        db: Database session
        user_id: ID of the owning user
        tenant_id: Tenant ID for RLS
        config_data: Configuration creation data

    Returns:
        Created TTSConfiguration
    """
    if config_data.is_default:
        await db.execute(
            sql_update(TTSConfiguration)
            .where(
                TTSConfiguration.user_id == user_id,
                TTSConfiguration.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )

    tts_config = TTSConfiguration(
        user_id=user_id,
        tenant_id=tenant_id,
        name=config_data.name,
        provider=config_data.provider,
        config=config_data.config,
        is_default=config_data.is_default,
    )
    db.add(tts_config)
    await db.commit()
    await db.refresh(tts_config)
    return tts_config


async def get_tts_configs(
    db: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[TTSConfiguration], int]:
    """
    List TTS configurations for a user with pagination.

    Args:
        db: Database session
        user_id: ID of the owning user
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        Tuple of (list of TTSConfiguration, total count)
    """
    count_result = await db.execute(
        select(func.count()).select_from(TTSConfiguration).where(
            TTSConfiguration.user_id == user_id
        )
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(TTSConfiguration)
        .where(TTSConfiguration.user_id == user_id)
        .order_by(TTSConfiguration.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    configs = list(result.scalars().all())
    return configs, total


async def get_tts_config_by_id(
    db: AsyncSession,
    config_id: UUID,
) -> Optional[TTSConfiguration]:
    """
    Get a TTS configuration by ID.

    Args:
        db: Database session
        config_id: UUID of the configuration

    Returns:
        TTSConfiguration or None if not found
    """
    return await db.get(TTSConfiguration, config_id)


async def update_tts_config(
    db: AsyncSession,
    tts_config: TTSConfiguration,
    update_data: TTSConfigUpdate,
) -> TTSConfiguration:
    """
    Update a TTS configuration with partial data.

    If is_default=True, clears the default flag on all other configs first.

    Args:
        db: Database session
        tts_config: Existing TTSConfiguration to update
        update_data: Update data (only provided fields updated)

    Returns:
        Updated TTSConfiguration
    """
    if update_data.is_default is True:
        await db.execute(
            sql_update(TTSConfiguration)
            .where(
                TTSConfiguration.user_id == tts_config.user_id,
                TTSConfiguration.id != tts_config.id,
                TTSConfiguration.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )

    update_fields = update_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(tts_config, field, value)

    await db.commit()
    await db.refresh(tts_config)
    return tts_config


async def delete_tts_config(
    db: AsyncSession,
    tts_config: TTSConfiguration,
) -> None:
    """
    Delete a TTS configuration.

    Args:
        db: Database session
        tts_config: TTSConfiguration to delete
    """
    await db.delete(tts_config)
    await db.commit()
