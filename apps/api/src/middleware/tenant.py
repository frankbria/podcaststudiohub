"""
Multi-tenant context injection middleware for Row-Level Security (RLS).

This middleware extracts tenant_id from JWT tokens and stores it in request.state
for use by the database dependency to configure PostgreSQL RLS context.
"""
import logging
from typing import Optional
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.middleware.auth import extract_token_from_header, get_tenant_id_from_token

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract tenant_id from JWT tokens and store in request state.

    This middleware:
    1. Extracts the JWT token from the Authorization header
    2. Gets the tenant_id from the token payload
    3. Stores tenant_id in request.state for use by get_db() dependency
    4. The get_db() dependency then sets PostgreSQL app.tenant_id for RLS

    Public endpoints (no authentication required) are skipped automatically.
    """

    # Public endpoints that don't require tenant context
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/auth/login",
        "/auth/register",
    }

    async def dispatch(self, request: Request, call_next):
        """
        Process each request to extract and store tenant context.

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response from the route handler
        """
        # Initialize tenant_id in request state
        request.state.tenant_id = None
        request.state.set_tenant_context = False

        # Skip tenant extraction for public endpoints
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Extract tenant_id from Authorization header
        try:
            token = await extract_token_from_header(request)
            if token:
                tenant_id = get_tenant_id_from_token(token)
                if tenant_id:
                    # Store tenant_id in request state for database dependency
                    request.state.tenant_id = tenant_id
                    request.state.set_tenant_context = True
        except ValueError:
            # Expected: invalid/expired token — continue without tenant context.
            # The auth dependency (get_current_user) handles the actual 401.
            logger.debug("Invalid token for %s", request.url.path)
        except HTTPException:
            # Auth-related HTTP errors must propagate (401, 403, etc.)
            raise
        except Exception as e:
            # Unexpected errors must be visible, not silently swallowed
            logger.error("Unexpected error in tenant middleware: %s", e, exc_info=True)
            raise

        # Continue to route handler
        response = await call_next(request)
        return response


def get_tenant_id(request: Request) -> Optional[str]:
    """
    Get tenant ID from request state.

    Args:
        request: FastAPI request object

    Returns:
        Tenant ID from request state or None if not set
    """
    return getattr(request.state, "tenant_id", None)
