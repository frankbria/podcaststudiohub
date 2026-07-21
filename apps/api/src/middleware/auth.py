"""JWT authentication middleware for protecting endpoints and extracting user context"""

from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from ..database import get_db
from ..services.auth_service import verify_jwt_token, verify_access_token
from ..models.user import User

# HTTPBearer with auto_error=False so missing credentials raise 401 (not 403)
security = HTTPBearer(auto_error=False)


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


def get_user_id_from_token(token: str) -> Optional[str]:
    """
    Softly extract the user id (``sub`` claim) from a JWT **access** token.

    Tolerant variant for boundary metering: returns None on any failure
    (invalid/expired token, wrong token type, missing claim) instead of raising,
    so it can run on every request without forcing authentication on public
    routes. Uses ``verify_access_token`` (not ``verify_jwt_token``) so refresh /
    verification tokens are not metered — they would be rejected with 401 by the
    route's ``get_current_user``, and metering must not pre-empt that with a 402.

    Args:
        token: JWT token string

    Returns:
        User ID string, or None if the token is not a valid access token.
    """
    try:
        return verify_access_token(token).get("sub")
    except Exception:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
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
        HTTPException 401: If no credentials, token invalid, or user not found
        HTTPException 403: If user account is inactive
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    try:
        # Decode and verify JWT token (must be an access token, not verification/refresh)
        payload = verify_access_token(token)
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

        # Store tenant_id from token so downstream RLS enforcement can read it
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
    Ensure the authenticated user's account is active.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        Active User model instance

    Raises:
        HTTPException 403: If the user account is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return current_user
