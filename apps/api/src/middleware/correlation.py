"""Request correlation ID middleware (issue #320).

Assigns every request an id, binds it to a contextvar so every log record
emitted while handling that request carries it, and echoes it back on the
response so a user-reported failure can be traced to its logs.

Registered LAST in main.py so it is OUTERMOST (Starlette applies
``add_middleware`` in LIFO order): the id must be bound before CORS and tenant
resolution run, or their own log lines would be uncorrelated.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.logging_config import CORRELATION_ID, REQUEST_ID_HEADER, TENANT_ID


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind an X-Request-ID to the request context and echo it on the response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Also on request.state so handlers can read it without importing the
        # contextvar, mirroring how tenant_id is exposed.
        request.state.request_id = request_id
        token = CORRELATION_ID.set(request_id)
        # Each request starts with no tenant; TenantContextMiddleware sets it
        # once the JWT is resolved. Reset here too so a recycled context can
        # never leak the previous request's tenant onto this one's logs.
        tenant_token = TENANT_ID.set(None)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            CORRELATION_ID.reset(token)
            TENANT_ID.reset(tenant_token)
