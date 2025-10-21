"""
JWT authentication middleware
"""
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from src.utils.jwt import verify_token, get_user_id_from_token, get_tenant_id_from_token


security = HTTPBearer()


async def verify_jwt_token(credentials: HTTPAuthorizationCredentials) -> dict:
    """
    Verify JWT token from Authorization header.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        Dictionary of token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials

    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_current_user_id(credentials: HTTPAuthorizationCredentials) -> str:
    """
    Extract user ID from JWT token.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        User ID from token

    Raises:
        HTTPException: If token is invalid or user ID missing
    """
    payload = await verify_jwt_token(credentials)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token",
        )

    return user_id


async def get_current_tenant_id(credentials: HTTPAuthorizationCredentials) -> str:
    """
    Extract tenant ID from JWT token.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        Tenant ID from token

    Raises:
        HTTPException: If token is invalid or tenant ID missing
    """
    payload = await verify_jwt_token(credentials)
    tenant_id = payload.get("tenant_id")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant ID not found in token",
        )

    return tenant_id


async def extract_token_from_header(request: Request) -> Optional[str]:
    """
    Extract JWT token from Authorization header.

    Args:
        request: FastAPI request object

    Returns:
        JWT token string if present, None otherwise
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    return auth_header.split(" ")[1]
