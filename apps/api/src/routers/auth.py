"""Authentication router for user registration and login"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..schemas.auth import UserRegister, UserLogin, UserResponse, TokenResponse
from ..services.auth_service import (
    create_user,
    authenticate_user,
    create_jwt_token,
    get_user_by_id
)
from ..models.user import User
from ..middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user account.

    - **email**: Valid email address (must be unique)
    - **password**: Minimum 8 characters with uppercase, lowercase, digit, and special character
    - **full_name**: User display name

    Returns JWT access token and user data.
    """
    try:
        # Create user in database (includes password hashing)
        user = await create_user(
            session=db,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name
        )

        # Generate JWT token
        access_token = create_jwt_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email
        )

        # Return token and user data
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=86400,  # 24 hours in seconds
            user=UserResponse.model_validate(user)
        )

    except HTTPException:
        # Re-raise HTTPExceptions from create_user (duplicate email, etc.)
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT access token.

    - **email**: Registered email address
    - **password**: Account password

    Returns JWT access token for API access.
    """
    # Authenticate user
    user = await authenticate_user(
        session=db,
        email=credentials.email,
        password=credentials.password
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact administrator."
        )

    # Generate JWT token
    access_token = create_jwt_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=86400,  # 24 hours in seconds
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information.

    Requires valid JWT token in Authorization header.
    Example: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    return UserResponse.model_validate(current_user)
