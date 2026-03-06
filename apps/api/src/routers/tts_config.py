"""
TTS configuration router for RESTful API endpoints.

Provides CRUD operations for TTS (text-to-speech) configurations.
All endpoints require authentication and enforce tenant isolation via RLS.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models import User
from ..schemas.tts_config import (
    TTSConfigCreate,
    TTSConfigUpdate,
    TTSConfigResponse,
    TTSConfigListResponse,
)
from ..services.tts_config_service import (
    create_tts_config,
    get_tts_configs,
    get_tts_config_by_id,
    update_tts_config,
    delete_tts_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts-configs", tags=["tts-configs"])


@router.post("", response_model=TTSConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_tts_config_endpoint(
    config_data: TTSConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new TTS configuration.

    Args:
        config_data: TTS configuration creation data
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Created TTS configuration with all fields
    """
    tts_config = await create_tts_config(
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
    List TTS configurations for the current user with pagination.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page (1-100)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Paginated list of TTS configurations
    """
    skip = (page - 1) * page_size
    configs, total = await get_tts_configs(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=page_size,
    )
    total_pages = (total + page_size - 1) // page_size

    return TTSConfigListResponse(
        tts_configs=configs,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{config_id}", response_model=TTSConfigResponse)
async def get_tts_config_endpoint(
    config_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a TTS configuration by ID.

    Args:
        config_id: UUID of the TTS configuration
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        TTS configuration details

    Raises:
        HTTPException: 404 if configuration not found or belongs to different user
    """
    tts_config = await get_tts_config_by_id(db=db, config_id=config_id)

    if tts_config is None or tts_config.user_id != current_user.id:
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
    Update a TTS configuration with partial data.

    Args:
        config_id: UUID of the TTS configuration
        update_data: Update data (only provided fields updated)
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        Updated TTS configuration

    Raises:
        HTTPException: 404 if configuration not found or belongs to different user
    """
    tts_config = await get_tts_config_by_id(db=db, config_id=config_id)

    if tts_config is None or tts_config.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TTS configuration not found",
        )

    updated_config = await update_tts_config(
        db=db,
        tts_config=tts_config,
        update_data=update_data,
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

    Args:
        config_id: UUID of the TTS configuration
        current_user: Authenticated user (from JWT token)
        db: Database session

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if configuration not found or belongs to different user
    """
    tts_config = await get_tts_config_by_id(db=db, config_id=config_id)

    if tts_config is None or tts_config.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TTS configuration not found",
        )

    await delete_tts_config(db=db, tts_config=tts_config)
    return None
