"""Authentication service for password hashing, JWT tokens, and user management"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4
import bcrypt
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from ..models.user import User
from ..config import settings


# ============================================================================
# Password Hashing Functions
# ============================================================================

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt for secure storage.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string (e.g., "$2b$12$...")
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a bcrypt hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to compare against

    Returns:
        True if password matches, False otherwise
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


# ============================================================================
# JWT Token Functions
# ============================================================================

def create_jwt_token(
    user_id: UUID,
    tenant_id: UUID,
    email: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token with user claims.

    Args:
        user_id: User's UUID
        tenant_id: User's tenant UUID for RLS enforcement
        email: User's email address
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),  # Subject (user ID)
        "tenant_id": str(tenant_id),  # For RLS enforcement in Task 2.4
        "email": email,
        "exp": expire,  # Expiration time
        "iat": datetime.utcnow(),  # Issued at
        "type": "access"  # Token type
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return token


def verify_jwt_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string to verify

    Returns:
        Decoded payload dictionary

    Raises:
        ValueError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {str(e)}")


# ============================================================================
# User Management Functions
# ============================================================================

async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    full_name: str
) -> User:
    """
    Create a new user with hashed password and unique tenant.

    Args:
        session: Database session
        email: User email (must be unique)
        password: Plain text password (will be hashed)
        full_name: User's display name

    Returns:
        Created User model instance

    Raises:
        HTTPException: If email already exists (400) or creation fails (500)
    """
    try:
        # Generate unique tenant_id for new user (each user is their own tenant)
        tenant_id = uuid4()

        # Create user with hashed password
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            tenant_id=tenant_id,
            is_active=True,
            is_verified=False,  # Email verification pending
            encrypted_api_keys={},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        session.add(user)
        await session.commit()

        return user

    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"User creation failed: {str(e)}"
        )


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str
) -> Optional[User]:
    """
    Authenticate user by email and password.

    Args:
        session: Database session
        email: User email address
        password: Plain text password

    Returns:
        User model instance if valid credentials, None otherwise
    """
    # Query user by email
    result = await session.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None

    # Verify password
    if not verify_password(password, user.password_hash):
        return None

    # Check if user is active
    if not user.is_active:
        return None

    # Set tenant context so the UPDATE is allowed by RLS, then update last_login
    await session.execute(text(f"SET LOCAL app.tenant_id = '{user.tenant_id}'"))
    user.last_login = datetime.utcnow()
    await session.commit()

    return user


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> Optional[User]:
    """
    Retrieve user by ID.

    Args:
        session: Database session
        user_id: User's UUID

    Returns:
        User model instance if found, None otherwise
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()
