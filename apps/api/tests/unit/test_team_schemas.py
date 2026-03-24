"""
Unit tests for team Pydantic schemas — no DB required.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from pydantic import ValidationError
from src.schemas.team import (
	TeamCreate,
	TeamUpdate,
	TeamMemberUpdate,
	InvitationCreate,
)


# ---------------------------------------------------------------------------
# TeamCreate
# ---------------------------------------------------------------------------


def test_team_create_valid():
	t = TeamCreate(name="My Team", description="A great team")
	assert t.name == "My Team"
	assert t.description == "A great team"


def test_team_create_name_required():
	with pytest.raises(ValidationError):
		TeamCreate(description="no name")


def test_team_create_empty_name_rejected():
	with pytest.raises(ValidationError):
		TeamCreate(name="")


def test_team_create_optional_fields_default_to_none():
	t = TeamCreate(name="Solo")
	assert t.description is None
	assert t.logo_url is None


# ---------------------------------------------------------------------------
# TeamUpdate
# ---------------------------------------------------------------------------


def test_team_update_all_optional():
	u = TeamUpdate()
	assert u.name is None
	assert u.description is None


def test_team_update_partial():
	u = TeamUpdate(name="New Name")
	assert u.name == "New Name"
	assert u.description is None


# ---------------------------------------------------------------------------
# TeamMemberUpdate
# ---------------------------------------------------------------------------


def test_member_update_valid_roles():
	for role in ("owner", "editor", "viewer", "analyst"):
		m = TeamMemberUpdate(role=role)
		assert m.role == role


def test_member_update_invalid_role():
	with pytest.raises(ValidationError):
		TeamMemberUpdate(role="superadmin")


# ---------------------------------------------------------------------------
# InvitationCreate
# ---------------------------------------------------------------------------


def test_invitation_create_valid():
	inv = InvitationCreate(email="user@example.com", role="editor")
	assert inv.email == "user@example.com"
	assert inv.role == "editor"


def test_invitation_create_invalid_email():
	with pytest.raises(ValidationError):
		InvitationCreate(email="not-an-email", role="editor")


def test_invitation_create_invalid_role():
	with pytest.raises(ValidationError):
		InvitationCreate(email="user@example.com", role="god")


def test_invitation_create_default_role():
	inv = InvitationCreate(email="user@example.com")
	assert inv.role == "editor"
