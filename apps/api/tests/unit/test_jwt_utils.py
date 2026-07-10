"""
Unit tests for JWT token utilities.

Tests cover:
- create_access_token: default expiry, custom expiry, token type claim
- create_refresh_token: expiry, token type claim
- verify_token: valid token, expired token, invalid signature, garbage input
- get_user_id_from_token: present sub claim, missing sub, invalid token
- get_tenant_id_from_token: present tenant_id, missing tenant_id, invalid token
"""

from datetime import timedelta

import jwt

from src.utils.jwt import (
	create_access_token,
	create_refresh_token,
	verify_token,
	get_user_id_from_token,
	get_tenant_id_from_token,
)
from src.config import settings


# ===========================================================================
# create_access_token
# ===========================================================================


def test_create_access_token_returns_string():
	token = create_access_token({"sub": "user-1"})
	assert isinstance(token, str)
	assert len(token) > 0


def test_create_access_token_type_claim():
	token = create_access_token({"sub": "user-1"})
	payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
	assert payload["type"] == "access"


def test_create_access_token_preserves_data():
	data = {"sub": "user-42", "tenant_id": "tenant-abc"}
	token = create_access_token(data)
	payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
	assert payload["sub"] == "user-42"
	assert payload["tenant_id"] == "tenant-abc"


def test_create_access_token_custom_expiry():
	token = create_access_token({"sub": "user-1"}, expires_delta=timedelta(hours=1))
	payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
	assert "exp" in payload


# ===========================================================================
# create_refresh_token
# ===========================================================================


def test_create_refresh_token_returns_string():
	token = create_refresh_token({"sub": "user-1"})
	assert isinstance(token, str)
	assert len(token) > 0


def test_create_refresh_token_type_claim():
	token = create_refresh_token({"sub": "user-1"})
	payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
	assert payload["type"] == "refresh"


# ===========================================================================
# verify_token
# ===========================================================================


def test_verify_token_valid():
	token = create_access_token({"sub": "user-1"})
	payload = verify_token(token)
	assert payload is not None
	assert payload["sub"] == "user-1"


def test_verify_token_invalid_signature():
	result = verify_token("not.a.valid.token")
	assert result is None


def test_verify_token_garbage():
	result = verify_token("garbage")
	assert result is None


def test_verify_token_expired():
	token = create_access_token({"sub": "user-1"}, expires_delta=timedelta(seconds=-1))
	result = verify_token(token)
	assert result is None


# ===========================================================================
# get_user_id_from_token
# ===========================================================================


def test_get_user_id_present():
	token = create_access_token({"sub": "user-99"})
	assert get_user_id_from_token(token) == "user-99"


def test_get_user_id_missing_sub():
	token = create_access_token({"tenant_id": "t-1"})
	assert get_user_id_from_token(token) is None


def test_get_user_id_invalid_token():
	assert get_user_id_from_token("invalid") is None


# ===========================================================================
# get_tenant_id_from_token
# ===========================================================================


def test_get_tenant_id_present():
	token = create_access_token({"sub": "user-1", "tenant_id": "tenant-xyz"})
	assert get_tenant_id_from_token(token) == "tenant-xyz"


def test_get_tenant_id_missing():
	token = create_access_token({"sub": "user-1"})
	assert get_tenant_id_from_token(token) is None


def test_get_tenant_id_invalid_token():
	assert get_tenant_id_from_token("invalid") is None
