"""Pydantic schemas for authentication"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from uuid import UUID


class UserRegister(BaseModel):
    """Schema for user registration"""
    email: EmailStr = Field(..., description="User email address (must be unique)")
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="User password (min 8 characters, must include uppercase, lowercase, digit, and special character)"
    )
    full_name: str = Field(..., min_length=1, max_length=255, description="User display name")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password contains required character types for security"""
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        # Check for special characters
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?/"
        if not any(char in special_chars for char in v):
            raise ValueError('Password must contain at least one special character')
        return v

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "email": "user@example.com",
            "password": "SecurePass123!",
            "full_name": "John Doe"
        }
    })


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "email": "user@example.com",
            "password": "SecurePass123!"
        }
    })


class UserResponse(BaseModel):
    """Schema for user response (excludes sensitive data)"""
    id: UUID
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_verified: bool
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Schema for authentication token response"""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="OAuth2 token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    user: UserResponse = Field(..., description="Authenticated user data")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 1800,
            "user": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "full_name": "John Doe",
                "is_active": True,
                "is_verified": False,
                "tenant_id": "123e4567-e89b-12d3-a456-426614174001",
                "created_at": "2025-11-11T00:00:00",
                "updated_at": "2025-11-11T00:00:00",
                "last_login": None
            }
        }
    })


class UserUpdate(BaseModel):
    """Schema for updating user profile"""
    full_name: Optional[str] = Field(None, max_length=255, description="Updated display name")

    model_config = ConfigDict(from_attributes=True)


class VerificationResponse(BaseModel):
    """Schema for email verification response"""
    message: str
    verified: bool


class AccountDeleteRequest(BaseModel):
    """Schema for confirming irreversible account erasure"""
    password: str = Field(..., description="Current password, re-entered to confirm erasure")


class ResendVerificationRequest(BaseModel):
    """Schema for resending a verification email"""
    email: EmailStr = Field(..., description="Email address to resend verification to")


class ResendVerificationResponse(BaseModel):
    """Schema for resend verification response"""
    message: str
    email: str
