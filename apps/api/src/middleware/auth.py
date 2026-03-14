"""JWT authentication middleware for protecting endpoints and extracting user context"""

from typing import Optional
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from ..database import get_db
from ..services.auth_service import verify_jwt_token, get_user_by_id
from ..models.user import User

# HTTPBearer security scheme for extracting Authorization header
security = HTTPBearer()


# =============================================================================
# Helper Functions for Token Extraction
# =============================================================================

async def extract_token_from_header(request: Request) -> Optional[str]:
    """
    Extract JWT token from Authorization header.

    Args:
        request: FastAPI request object

    Returns:
        JWT token string or None if not present
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    # Extract token from "Bearer <token>" format
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def get_tenant_id_from_token(token: str) -> Optional[str]:
    """
    Extract tenant_id from JWT token payload.

    Args:
        token: JWT token string

    Returns:
        Tenant ID string or None if tenant_id claim is missing

    Raises:
        ValueError: If token is invalid or expired (from verify_jwt_token)
    """
    payload = verify_jwt_token(token)
    return payload.get("tenant_id")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Extract and validate JWT token from Authorization header.
    Returns authenticated User model instance.

    Usage in endpoints:
        @router.get("/protected")
        async def protected_endpoint(user: User = Depends(get_current_user)):
            return {"user_id": user.id, "email": user.email}

    Args:
        credentials: HTTP Bearer token from Authorization header
        db: Database session

    Returns:
        Authenticated User model instance

    Raises:
        HTTPException 401: If token is invalid or user not found
        HTTPException 403: If user account is inactive
    """
    token = credentials.credentials

    try:
        # Decode and verify JWT token
        payload = verify_jwt_token(token)
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Retrieve user from database
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account"
            )

        # Store tenant_id from token for RLS context (Task 2.4 will use this)
        # This allows middleware to enforce row-level security
        user._tenant_id_from_token = tenant_id

        return user

    except ValueError as e:
        # Token verification failed (invalid signature, expired, etc.)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Ensure user is active and verified.

    Optional additional layer of validation for endpoints that require
    verified accounts.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        Active User model instance

    Raises:
        HTTPException 403: If user is inactive or unverified
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    # Optional: Enforce email verification
    # if not current_user.is_verified:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Email not verified"
    #     )

    return current_user


async def get_current_user_from_query(
    token: Optional[str] = Query(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate user from JWT token in query parameter or Authorization header.

    This dependency is specifically designed for SSE (Server-Sent Events) endpoints.
    The browser's EventSource API does not support custom headers by the W3C spec,
    so JWT tokens cannot be sent via the standard Authorization header. Instead,
    the token is accepted as a URL query parameter: ?token=<jwt>.

    The dependency falls back to the Authorization header for backward compatibility,
    allowing standard HTTP clients to authenticate with both methods. When both are
    present, the query parameter token takes precedence.

    Security considerations:
    - Tokens in query parameters may appear in server logs and browser history.
      HTTPS must be enforced in production to prevent token interception.
    - Token expiration (30 minutes) still applies, same as header-based auth.
    - Use this dependency ONLY for SSE endpoints; standard endpoints should use
      get_current_user (header-only) for security.

    Args:
        token: JWT token from query parameter (for SSE/EventSource clients)
        request: FastAPI request object (used to check Authorization header)
        db: Database session

    Returns:
        Authenticated User model instance

    Raises:
        HTTPException 401: If no token provided, token is invalid, or user not found
        HTTPException 403: If user account is inactive
    """
    # Prefer query param token (SSE use case); fall back to Authorization header
    jwt_token = token
    if not jwt_token and request is not None:
        jwt_token = await extract_token_from_header(request)

    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Decode and verify JWT token
        payload = verify_jwt_token(jwt_token)
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Retrieve user from database
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account"
            )

        # Store tenant_id from token for RLS context
        user._tenant_id_from_token = tenant_id

        return user

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
