"""
FastAPI dependency injection helpers

This module re-exports authentication dependencies from middleware for backwards compatibility.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Re-export authentication dependencies from middleware
from src.middleware.auth import get_current_user, get_active_user

# Database dependency
from src.database import get_db, set_tenant_context


async def get_db_with_tenant(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
) -> AsyncSession:
    """
    Dependency to get database session with tenant context set from current user.

    Usage:
        @app.get("/projects")
        async def list_projects(db: AsyncSession = Depends(get_db_with_tenant)):
            # RLS policies will automatically filter by tenant_id
            result = await db.execute(select(Project))
            return result.scalars().all()

    Args:
        db: Database session
        current_user: Current authenticated user (includes tenant_id)

    Returns:
        Database session with tenant context set

    Note:
        This will be enhanced in Task 2.4 to use tenant_id from JWT token
    """
    # Set tenant context from authenticated user
    tenant_id = str(current_user.tenant_id)
    await set_tenant_context(db, tenant_id)
    return db


__all__ = [
    "get_current_user",
    "get_active_user",
    "get_db",
    "get_db_with_tenant",
]
