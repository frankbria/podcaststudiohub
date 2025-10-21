"""
FastAPI dependency injection helpers
"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.database import get_db
from src.middleware.auth import get_current_user_id, get_current_tenant_id


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Dependency to get the current authenticated user ID.

    Usage:
        @app.get("/me")
        async def read_current_user(user_id: str = Depends(get_current_user)):
            return {"user_id": user_id}

    Args:
        credentials: HTTP authorization credentials from request

    Returns:
        User ID from JWT token

    Raises:
        HTTPException: If authentication fails
    """
    return await get_current_user_id(credentials)


async def get_tenant_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Dependency to get the current tenant ID.

    Usage:
        @app.get("/projects")
        async def list_projects(tenant_id: str = Depends(get_tenant_id)):
            # Projects will be automatically filtered by RLS
            return {"tenant_id": tenant_id}

    Args:
        credentials: HTTP authorization credentials from request

    Returns:
        Tenant ID from JWT token

    Raises:
        HTTPException: If authentication fails or tenant ID missing
    """
    return await get_current_tenant_id(credentials)


async def get_db_with_tenant(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> AsyncSession:
    """
    Dependency to get database session with tenant context set.

    Usage:
        @app.get("/projects")
        async def list_projects(db: AsyncSession = Depends(get_db_with_tenant)):
            # RLS policies will automatically filter by tenant_id
            result = await db.execute(select(Project))
            return result.scalars().all()

    Args:
        db: Database session
        tenant_id: Tenant ID from JWT token

    Returns:
        Database session with tenant context
    """
    from src.database import set_tenant_context
    await set_tenant_context(db, tenant_id)
    return db


async def get_optional_user(
    request: Request,
) -> Optional[str]:
    """
    Dependency to optionally get the current user ID.
    Returns None if no valid token is present.

    Usage:
        @app.get("/public")
        async def public_endpoint(user_id: Optional[str] = Depends(get_optional_user)):
            if user_id:
                return {"message": f"Hello, {user_id}"}
            return {"message": "Hello, guest"}

    Args:
        request: FastAPI request object

    Returns:
        User ID if authenticated, None otherwise
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    try:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=auth_header.split(" ")[1]
        )
        return await get_current_user_id(credentials)
    except HTTPException:
        return None
