"""
Credential encryption utilities using PostgreSQL pgcrypto
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.config import settings


async def encrypt_credential(db: AsyncSession, credential: str) -> str:
    """
    Encrypt a credential using PostgreSQL pgcrypto.

    Args:
        db: Async database session
        credential: Plain text credential to encrypt

    Returns:
        Base64-encoded encrypted credential
    """
    result = await db.execute(
        text("SELECT encrypt_credential(:credential, :key)"),
        {"credential": credential, "key": settings.ENCRYPTION_KEY}
    )
    return result.scalar_one()


async def decrypt_credential(db: AsyncSession, encrypted_credential: str) -> str:
    """
    Decrypt a credential using PostgreSQL pgcrypto.

    Args:
        db: Async database session
        encrypted_credential: Base64-encoded encrypted credential

    Returns:
        Decrypted plain text credential
    """
    result = await db.execute(
        text("SELECT decrypt_credential(:encrypted_credential, :key)"),
        {"encrypted_credential": encrypted_credential, "key": settings.ENCRYPTION_KEY}
    )
    return result.scalar_one()


async def encrypt_api_keys(db: AsyncSession, api_keys: dict) -> dict:
    """
    Encrypt multiple API keys for storage in JSONB column.

    Args:
        db: Async database session
        api_keys: Dictionary of API key names to plain text keys

    Returns:
        Dictionary of API key names to encrypted keys
    """
    encrypted_keys = {}
    for key_name, key_value in api_keys.items():
        if key_value:
            encrypted_keys[key_name] = await encrypt_credential(db, key_value)
    return encrypted_keys


async def decrypt_api_keys(db: AsyncSession, encrypted_keys: dict) -> dict:
    """
    Decrypt multiple API keys from JSONB column.

    Args:
        db: Async database session
        encrypted_keys: Dictionary of API key names to encrypted keys

    Returns:
        Dictionary of API key names to plain text keys
    """
    decrypted_keys = {}
    for key_name, encrypted_value in encrypted_keys.items():
        if encrypted_value:
            decrypted_keys[key_name] = await decrypt_credential(db, encrypted_value)
    return decrypted_keys
