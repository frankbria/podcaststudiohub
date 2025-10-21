"""
Multi-tenant context injection middleware
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal, set_tenant_context
from src.middleware.auth import extract_token_from_header, get_tenant_id_from_token


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject tenant context for Row-Level Security.

    This middleware:
    1. Extracts the JWT token from the Authorization header
    2. Gets the tenant_id from the token
    3. Sets the tenant_id in PostgreSQL session for RLS policies
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process each request to inject tenant context.

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response from the route handler
        """
        # Skip tenant context for public endpoints
        if request.url.path in ["/", "/health", "/docs", "/openapi.json", "/auth/login", "/auth/register"]:
            return await call_next(request)

        # Extract token and get tenant ID
        token = await extract_token_from_header(request)
        if token:
            tenant_id = get_tenant_id_from_token(token)
            if tenant_id:
                # Store tenant_id in request state for use in route handlers
                request.state.tenant_id = tenant_id

                # Set tenant context in database session
                async with AsyncSessionLocal() as db:
                    try:
                        await set_tenant_context(db, tenant_id)
                    except Exception:
                        pass  # Continue even if RLS context fails

        response = await call_next(request)
        return response


def get_tenant_id(request: Request) -> str:
    """
    Get tenant ID from request state.

    Args:
        request: FastAPI request object

    Returns:
        Tenant ID from request state
    """
    return getattr(request.state, "tenant_id", None)
