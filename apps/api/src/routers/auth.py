"""Authentication router for user registration and login"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, set_tenant_context
from ..schemas.auth import (
    ResendVerificationRequest,
    ResendVerificationResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    VerificationResponse,
)
from ..services.auth_service import (
    authenticate_user,
    create_jwt_token,
    create_user,
    create_verification_token,
    get_user_by_email,
    mark_user_verified,
    verify_verification_token,
)
from ..services.email_service import send_verification_email
from ..models.user import User
from ..middleware.auth import get_current_user
from ..dependencies import create_rate_limit_dependency
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Rate limit dependencies — instantiated once at import time
_rate_limit_login = create_rate_limit_dependency(
    "login",
    settings.RATE_LIMIT_LOGIN_REQUESTS,
    settings.RATE_LIMIT_LOGIN_WINDOW_MINUTES,
)
_rate_limit_register = create_rate_limit_dependency(
    "register",
    settings.RATE_LIMIT_REGISTER_REQUESTS,
    settings.RATE_LIMIT_REGISTER_WINDOW_MINUTES,
)
_rate_limit_resend = create_rate_limit_dependency(
    "resend",
    settings.RATE_LIMIT_RESEND_REQUESTS,
    settings.RATE_LIMIT_RESEND_WINDOW_MINUTES,
)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_rate_limit_register),
):
    """
    Register a new user account.

    - **email**: Valid email address (must be unique)
    - **password**: Minimum 8 characters with uppercase, lowercase, digit, and special character
    - **full_name**: User display name

    Returns JWT access token and user data. A verification email is sent asynchronously;
    the user must verify their email before logging in.
    """
    try:
        # Create user in database (includes password hashing)
        user = await create_user(
            session=db,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name
        )

        # Send verification email (failure is non-fatal)
        verification_token = create_verification_token(user.id, user.email, user.tenant_id)
        sent = await send_verification_email(user.email, user.full_name or user.email, verification_token)
        if not sent:
            logger.warning("Failed to send verification email to %s", user.email)

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
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_rate_limit_login),
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

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your email for the verification link.",
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


@router.get("/verify-email", response_model=VerificationResponse)
async def verify_email(
    token: str = Query(..., description="Email verification token from the link in your inbox"),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a user's email address using the token sent during registration.

    - **token**: JWT verification token (from the ?token= query parameter in the email link)

    Returns 200 on success, 400 for invalid/expired tokens, 404 if user not found.
    """
    try:
        payload = verify_verification_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    try:
        user_id = UUID(payload["sub"])
        tenant_id = payload["tenant_id"]
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    # Set RLS context so the UPDATE is visible to PostgreSQL row-level security
    await set_tenant_context(db, tenant_id)

    # mark_user_verified raises 404 if user not found
    await mark_user_verified(db, user_id)

    return VerificationResponse(message="Email verified successfully.", verified=True)


@router.post("/resend-verification-email", response_model=ResendVerificationResponse, status_code=status.HTTP_200_OK)
async def resend_verification_email(
    body: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_rate_limit_resend),
):
    """
    Resend the email verification link to the given email address.

    - **email**: Email address of the unverified account

    Always returns 200 with a generic message to prevent user enumeration —
    callers cannot tell whether an account exists or is already verified.
    Rate limited to prevent abuse.
    """
    _GENERIC_MESSAGE = "If an unverified account exists for that address, a verification email has been sent."

    user = await get_user_by_email(db, body.email)

    if user is None or user.is_verified:
        # Return generic 200 — do not reveal whether the address is registered
        return ResendVerificationResponse(
            message=_GENERIC_MESSAGE,
            email=body.email,
        )

    verification_token = create_verification_token(user.id, user.email, user.tenant_id)
    sent = await send_verification_email(user.email, user.full_name or user.email, verification_token)
    if not sent:
        logger.warning("Failed to resend verification email to %s", user.email)

    return ResendVerificationResponse(
        message=_GENERIC_MESSAGE,
        email=user.email,
    )
