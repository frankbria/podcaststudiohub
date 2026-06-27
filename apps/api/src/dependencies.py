"""
FastAPI dependency injection helpers

This module provides authentication and tenant context dependencies.
"""
import logging
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

# Re-export authentication dependencies from middleware
from src.middleware.auth import (
	extract_token_from_header,
	get_active_user,
	get_current_user,
	get_user_id_from_token,
)
from src.middleware.tenant import TenantContextMiddleware
from src.services import usage_service

# Database dependency
from src.database import get_db

logger = logging.getLogger(__name__)


async def meter_api_call(
	request: Request, db: AsyncSession = Depends(get_db)
) -> None:
	"""Global boundary hook: enforce and record the per-period API-call quota.

	Runs on every route via the app-level dependency. It is a no-op for public
	paths and unauthenticated requests, so it never forces auth. For authenticated
	requests it reuses the RLS-aware, test-overridable ``get_db`` session to check
	``check_api_limit`` (→ 402 when over) and then ``track_api_call``.

	ponytail: depends on get_db so it opens a session even on public paths; kept
	this way for test-overridability — swap to a lazy session if health-check DB
	load ever matters.
	"""
	if request.url.path in TenantContextMiddleware.PUBLIC_PATHS:
		return

	token = await extract_token_from_header(request)
	if not token:
		return

	user_id = get_user_id_from_token(token)
	tenant_id = getattr(request.state, "tenant_id", None)
	if not user_id or not tenant_id:
		# Unauthenticated / unresolved tenant — let the route's auth handle it.
		return

	try:
		uid = UUID(user_id)
		tid = UUID(tenant_id)
	except (ValueError, TypeError):
		return

	# Always meter the call. Enforce the cap everywhere EXCEPT the billing
	# endpoints — otherwise an over-quota user is bricked: they could neither see
	# their usage nor upgrade to escape the cap (the recovery path itself 402s).
	try:
		if not request.url.path.startswith("/billing"):
			if not await usage_service.check_api_limit(db, uid):
				raise HTTPException(
					status_code=status.HTTP_402_PAYMENT_REQUIRED,
					detail="Monthly API call limit reached for your plan. Please upgrade.",
				)
		await usage_service.track_api_call(db, uid, tid)
	except IntegrityError:
		# billing_usage's only FK is user_id, so this means the token's subject no
		# longer exists (user deleted after token issue). That is an auth condition,
		# not a billing failure — roll back and let get_current_user return 401.
		await db.rollback()


def create_rate_limit_dependency(key_prefix: str, max_requests: int, window_minutes: int):
	"""
	Factory that returns a FastAPI dependency enforcing a rate limit.

	The returned dependency extracts the client IP (honouring
	``X-Forwarded-For`` when proxy trust is enabled), calls the shared
	:class:`RateLimiter`, and raises HTTP 429 when the limit is exceeded.

	Args:
		key_prefix: Short name used as the Redis key namespace (e.g. ``"login"``).
		max_requests: Maximum requests allowed in the window.
		window_minutes: Window length in minutes.

	Returns:
		An async FastAPI dependency callable.
	"""
	async def _rate_limit_dependency(request: Request) -> None:
		from src.config import settings
		from src.services.rate_limiter import RateLimiter, get_client_ip

		if not settings.RATE_LIMIT_ENABLED:
			return

		client_ip = get_client_ip(
			client_host=request.client.host if request.client else None,
			forwarded_for=request.headers.get("X-Forwarded-For"),
			trust_proxy=settings.RATE_LIMIT_TRUST_PROXY,
			proxy_count=settings.RATE_LIMIT_PROXY_COUNT,
		)

		limiter = RateLimiter(settings.REDIS_URL)
		key = f"{key_prefix}:{client_ip}"
		allowed, info = limiter.is_allowed(
			key=key,
			max_requests=max_requests,
			window_seconds=window_minutes * 60,
		)

		if not allowed:
			retry_after = info.get("retry_after", window_minutes * 60)
			logger.warning(
				"Rate limit exceeded: endpoint=%s ip=%s retry_after=%s",
				key_prefix,
				client_ip,
				retry_after,
			)
			raise HTTPException(
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				detail="Too many requests. Please try again later.",
				headers={"Retry-After": str(retry_after)},
			)

	return _rate_limit_dependency


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
    "create_rate_limit_dependency",
    "meter_api_call",
]
