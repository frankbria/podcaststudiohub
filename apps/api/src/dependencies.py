"""
FastAPI dependency injection helpers
"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from src.database import get_db
from src.middleware.auth import get_current_user_id as get_user_id_from_auth, get_current_tenant_id
from src.models.user import User


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency to get the current authenticated user object.

    Usage:
        @app.get("/me")
        async def read_current_user(user: User = Depends(get_current_user)):
            return user

    Args:
        credentials: HTTP authorization credentials from request
        db: Database session

    Returns:
        User object from database

    Raises:
        HTTPException: If authentication fails or user not found
    """
    user_id = await get_user_id_from_auth(credentials)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Dependency to get the current authenticated user ID.

    Usage:
        @app.get("/data")
        async def read_data(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id}

    Args:
        credentials: HTTP authorization credentials from request

    Returns:
        User ID from JWT token

    Raises:
        HTTPException: If authentication fails
    """
    return await get_user_id_from_auth(credentials)


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
        return await get_user_id_from_auth(credentials)
    except HTTPException:
        return None
