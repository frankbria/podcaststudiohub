"""
FastAPI dependency injection helpers

This module provides authentication and tenant context dependencies.
"""
from fastapi import Depends, HTTPException, Request, status
from uuid import UUID

# Re-export authentication dependencies from middleware
from src.middleware.auth import get_current_user, get_active_user

# Database dependency
from src.database import get_db


def get_current_tenant(request: Request) -> UUID:
    """
    Extract tenant_id from request state (set by TenantContextMiddleware).

    This dependency should be used in route handlers that need tenant_id
    but don't necessarily need the full authenticated user.

    Usage in routes:
        @router.get("/projects")
        async def list_projects(
            tenant_id: UUID = Depends(get_current_tenant),
            db: AsyncSession = Depends(get_db)
        ):
            # tenant_id is available here
            # RLS policies also enforce tenant isolation in db queries

    Args:
        request: FastAPI request object (injected automatically)

    Returns:
        UUID of the current tenant

    Raises:
        HTTPException 401: If tenant context not found (not authenticated)
    """
    if not hasattr(request.state, 'tenant_id') or not request.state.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context not found. Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return UUID(request.state.tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant ID format",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_tenant_from_user(current_user = Depends(get_current_user)) -> UUID:
    """
    Get tenant_id from authenticated user.

    This is a more secure alternative to get_current_tenant as it validates
    authentication first through the full authentication flow.

    Usage in routes:
        @router.get("/projects")
        async def list_projects(
            tenant_id: UUID = Depends(get_current_tenant_from_user),
            db: AsyncSession = Depends(get_db)
        ):
            # tenant_id is from authenticated user

    Args:
        current_user: Current authenticated user (injected by get_current_user)

    Returns:
        UUID of the tenant associated with the user
    """
    return current_user.tenant_id


__all__ = [
    "get_current_user",
    "get_active_user",
    "get_db",
    "get_current_tenant",
    "get_current_tenant_from_user",
]
