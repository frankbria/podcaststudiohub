"""Authentication service for user management"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.user import User
from ..schemas.auth import UserCreate, TokenResponse
from ..utils.jwt import create_access_token, create_refresh_token
from ..config import settings


class AuthService:
    """Service for handling authentication operations"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        """Hash a plain password"""
        # Truncate to 72 bytes to avoid bcrypt limitation
        # This is a bcrypt requirement and considered best practice
        password_bytes = password.encode('utf-8')[:72]
        password_truncated = password_bytes.decode('utf-8', errors='ignore')
        return self.pwd_context.hash(password_truncated)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its hash"""
        # Truncate to 72 bytes to match hash_password behavior
        password_bytes = plain_password.encode('utf-8')[:72]
        password_truncated = password_bytes.decode('utf-8', errors='ignore')
        return self.pwd_context.verify(password_truncated, hashed_password)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email address"""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def register(self, user_data: UserCreate) -> User:
        """Register a new user"""
        # Check if user already exists
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Create new tenant_id for this user (for multi-tenancy)
        tenant_id = uuid4()

        # Create new user
        user = User(
            email=user_data.email,
            password_hash=self.hash_password(user_data.password),
            full_name=user_data.full_name,
            tenant_id=tenant_id,
            is_active=True,
            is_verified=False,  # Email verification would be implemented separately
            encrypted_api_keys={},
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def login(self, email: str, password: str) -> TokenResponse:
        """Authenticate user and return tokens"""
        # Get user by email
        user = await self.get_user_by_email(email)
        if not user:
            raise ValueError("Invalid email or password")

        # Verify password
        if not self.verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        # Check if user is active
        if not user.is_active:
            raise ValueError("User account is disabled")

        # Update last login
        user.last_login = datetime.utcnow()
        await self.db.commit()

        # Create tokens
        access_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id),
        }

        access_token = create_access_token(access_token_data)
        refresh_token = create_refresh_token(access_token_data)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate user by email and password"""
        user = await self.get_user_by_email(email)
        if not user:
            return None

        if not self.verify_password(password, user.password_hash):
            return None

        return user
