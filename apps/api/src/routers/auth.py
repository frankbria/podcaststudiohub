"""Authentication router for user registration and login"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.auth import UserCreate, UserLogin, UserResponse, TokenResponse
from ..services.auth_service import AuthService
from ..dependencies import get_current_user
from ..models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user

    Creates a new user account with encrypted password and generates a unique tenant_id
    for multi-tenancy isolation.
    """
    auth_service = AuthService(db)

    try:
        user = await auth_service.register(user_data)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and return JWT tokens

    Returns access and refresh tokens for API authentication.
    """
    auth_service = AuthService(db)

    try:
        tokens = await auth_service.login(credentials.email, credentials.password)
        return tokens
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user information

    Requires valid JWT token in Authorization header.
    """
    return current_user
