"""
FastAPI dependency injection helpers

This module provides authentication and tenant context dependencies.
"""
import logging
from fastapi import Depends, HTTPException, Request, status
from uuid import UUID

# Re-export authentication dependencies from middleware
from src.middleware.auth import get_current_user, get_active_user

# Database dependency
from src.database import get_db

# Rate limiting service
from src.services.rate_limiter import check_rate_limit, get_client_identifier
from src.config import settings

logger = logging.getLogger(__name__)


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


def create_rate_limit_dependency(key_prefix: str, max_requests: int, window_minutes: int):
    """
    Factory that returns a FastAPI dependency callable for rate limiting.

    Args:
        key_prefix: Identifier prefix for the rate limit key (e.g., "login", "register")
        max_requests: Maximum allowed requests within the window
        window_minutes: Time window length in minutes

    Returns:
        An async callable suitable for use with FastAPI Depends()
    """
    async def _rate_limit(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_ip = get_client_identifier(request)
        key = f"rate_limit:{key_prefix}:{client_ip}"
        window_seconds = window_minutes * 60

        allowed, info = check_rate_limit(key, max_requests, window_seconds)

        # Store info on request state so middleware can attach response headers
        request.state.rate_limit_info = {
            "limit": max_requests,
            "remaining": info.get("remaining", 0),
            "window_seconds": window_seconds,
        }

        if not allowed:
            retry_after = info.get("retry_after", window_seconds)
            logger.warning(
                "Rate limit exceeded for %s: %s (retry_after=%ss)",
                key_prefix,
                client_ip,
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    return _rate_limit


# Pre-built dependency instances for auth endpoints
rate_limit_login = create_rate_limit_dependency(
    "login",
    settings.RATE_LIMIT_LOGIN_REQUESTS,
    settings.RATE_LIMIT_LOGIN_WINDOW_MINUTES,
)

rate_limit_register = create_rate_limit_dependency(
    "register",
    settings.RATE_LIMIT_REGISTER_REQUESTS,
    settings.RATE_LIMIT_REGISTER_WINDOW_MINUTES,
)

rate_limit_resend = create_rate_limit_dependency(
    "resend",
    settings.RATE_LIMIT_RESEND_REQUESTS,
    settings.RATE_LIMIT_RESEND_WINDOW_MINUTES,
)


__all__ = [
    "get_current_user",
    "get_active_user",
    "get_db",
    "get_current_tenant",
    "get_current_tenant_from_user",
    "create_rate_limit_dependency",
    "rate_limit_login",
    "rate_limit_register",
    "rate_limit_resend",
]
