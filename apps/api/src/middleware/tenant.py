"""
Multi-tenant context injection middleware for Row-Level Security (RLS).

This middleware extracts tenant_id from JWT tokens and stores it in request.state
for use by the database dependency to configure PostgreSQL RLS context.
"""
import logging
from typing import Optional
from fastapi import HTTPException, Request
from jose import JWTError
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
        except (ValueError, KeyError, JWTError):
            # Expected failures: invalid token format, missing claims, JWT decode error.
            # Continue without tenant context; the auth middleware will reject the request
            # on protected endpoints.
            logger.debug("Invalid token format for %s", request.url.path)
        except HTTPException:
            # HTTP exceptions (401, 403, etc.) must propagate to the client.
            raise
        except Exception as e:
            # Unexpected errors (e.g. database issues, programming bugs) must be
            # logged and re-raised so they produce a 500 response rather than
            # silently succeeding with missing tenant context.
            logger.error(
                "Unexpected error in tenant middleware for %s: %s",
                request.url.path,
                e,
                exc_info=True,
            )
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
