"""Authentication service for password hashing, JWT tokens, and user management"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4
import bcrypt
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from sqlalchemy.orm.attributes import flag_modified

from ..models.user import User
from ..config import settings
from ..utils.encryption import encrypt_credential, decrypt_credential


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

    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": str(user_id),  # Subject (user ID)
        "tenant_id": str(tenant_id),  # For RLS enforcement in Task 2.4
        "email": email,
        "exp": expire,  # Expiration time
        "iat": datetime.now(timezone.utc),  # Issued at
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


def verify_access_token(token: str) -> dict:
    """
    Decode and validate a JWT *access* token.

    Unlike verify_jwt_token, this enforces that the token's `type` claim is
    'access', so long-lived verification (24h) and refresh (7d) tokens — which
    are signed with the same JWT_SECRET_KEY — cannot be used as API access
    credentials (see issue #205).

    Args:
        token: JWT token string to verify

    Returns:
        Decoded payload dictionary

    Raises:
        ValueError: If token is invalid, expired, or not an access token
    """
    payload = verify_jwt_token(token)  # raises ValueError on bad token

    if payload.get("type") != "access":
        raise ValueError("Invalid token type")

    return payload


# ============================================================================
# Email Verification Token Functions
# ============================================================================

def create_verification_token(user_id: UUID, email: str, tenant_id: UUID) -> str:
    """
    Create a short-lived JWT token for email verification.

    Args:
        user_id: User's UUID
        email: User's email address
        tenant_id: User's tenant UUID (required to set RLS context during verification)

    Returns:
        Encoded JWT token string (expires in EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": str(user_id),
        "email": email,
        "tenant_id": str(tenant_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "verification",
    }

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_verification_token(token: str) -> dict:
    """
    Decode and validate an email verification JWT token.

    Args:
        token: JWT verification token string

    Returns:
        Decoded payload dict containing 'sub' (user_id) and 'email'

    Raises:
        ValueError: If token is invalid, expired, or wrong type
    """
    payload = verify_jwt_token(token)  # raises ValueError on bad token

    if payload.get("type") != "verification":
        raise ValueError("Invalid token type")

    return payload


async def mark_user_verified(session: AsyncSession, user_id: UUID) -> "User":
    """
    Mark a user as email-verified.

    Args:
        session: Database session
        user_id: User's UUID

    Returns:
        Updated User instance

    Raises:
        HTTPException: 404 if user not found
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_verified = True
    user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()

    return user


async def get_user_by_email(session: AsyncSession, email: str) -> Optional["User"]:
    """
    Retrieve a user by email address.

    Args:
        session: Database session
        email: Email address to look up

    Returns:
        User instance or None if not found
    """
    # Case-insensitive lookup: email is not identity-significant by case (#255);
    # the function lowercases both sides, matching legacy mixed-case rows too.
    # Goes through the SECURITY DEFINER auth_lookup_user_by_email function
    # (migration 014) because login/resend-verification run before any tenant
    # context exists — the blanket users SELECT policy is gone (issue #304).
    result = await session.execute(
        select(User).from_statement(
            text("SELECT * FROM auth_lookup_user_by_email(:email)")
        ),
        {"email": email},
    )
    return result.scalar_one_or_none()


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

        # Arm the new tenant's RLS context before the INSERT: registration is
        # the one pre-tenant write, and since migration 014 the INSERT must
        # satisfy WITH CHECK (tenant_id = current_setting('app.tenant_id')).
        from ..database import set_tenant_context
        await set_tenant_context(session, str(tenant_id))

        # Canonicalize email to lowercase so case is never identity-significant (#255).
        email = email.lower()

        # Create user with hashed password
        user = User(
            id=uuid4(),
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            tenant_id=tenant_id,
            is_active=True,
            is_verified=not settings.EMAIL_ENABLED,  # Auto-verify when email is disabled
            encrypted_api_keys={},
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
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
    # Pre-tenant lookup via the SECURITY DEFINER function (case-insensitive)
    user = await get_user_by_email(session, email)

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
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
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


# ============================================================================
# API Key Encryption Functions
# ============================================================================

async def store_api_key(
    session: AsyncSession,
    user_id: UUID,
    provider: str,
    api_key: str,
) -> None:
    """
    Encrypt and store an API key for a third-party provider.

    Args:
        session: Database session
        user_id: User's UUID
        provider: Provider name (e.g. "openai", "elevenlabs", "gemini")
        api_key: Plain text API key to encrypt and store

    Raises:
        HTTPException: 404 if user not found
    """
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    encrypted = await encrypt_credential(session, api_key)

    if user.encrypted_api_keys is None:
        user.encrypted_api_keys = {}

    user.encrypted_api_keys[provider] = encrypted
    flag_modified(user, "encrypted_api_keys")
    await session.commit()


async def get_api_key(
    session: AsyncSession,
    user_id: UUID,
    provider: str,
) -> Optional[str]:
    """
    Retrieve and decrypt an API key for a provider.

    Args:
        session: Database session
        user_id: User's UUID
        provider: Provider name

    Returns:
        Decrypted API key string, or None if provider not stored

    Raises:
        HTTPException: 404 if user not found
    """
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    encrypted = (user.encrypted_api_keys or {}).get(provider)
    if encrypted is None:
        return None

    return await decrypt_credential(session, encrypted)


async def delete_api_key(
    session: AsyncSession,
    user_id: UUID,
    provider: str,
) -> bool:
    """
    Remove the stored API key for a provider.

    Args:
        session: Database session
        user_id: User's UUID
        provider: Provider name to remove

    Returns:
        True if the key was deleted, False if provider wasn't stored

    Raises:
        HTTPException: 404 if user not found
    """
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if provider not in (user.encrypted_api_keys or {}):
        return False

    del user.encrypted_api_keys[provider]
    flag_modified(user, "encrypted_api_keys")
    await session.commit()
    return True


async def list_api_key_providers(
    session: AsyncSession,
    user_id: UUID,
) -> list[str]:
    """
    List provider names that have stored API keys (no key values).

    Args:
        session: Database session
        user_id: User's UUID

    Returns:
        List of provider name strings

    Raises:
        HTTPException: 404 if user not found
    """
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return list((user.encrypted_api_keys or {}).keys())
