"""
Unit tests for rbac_service.py — pure permission-matrix logic (no DB required).
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("ENCRYPTION_KEY", "a" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

from src.services.rbac_service import role_has_permission, ROLE_PERMISSIONS


# ---------------------------------------------------------------------------
# role_has_permission
# ---------------------------------------------------------------------------


def test_owner_has_all_write_permissions():
	for perm in ["projects.create", "projects.edit", "projects.delete", "team.manage_members"]:
		assert role_has_permission("owner", perm) is True


def test_editor_cannot_delete_project():
	assert role_has_permission("editor", "projects.delete") is False


def test_editor_can_create_and_edit_episodes():
	assert role_has_permission("editor", "episodes.create") is True
	assert role_has_permission("editor", "episodes.edit") is True


def test_editor_cannot_manage_members():
	assert role_has_permission("editor", "team.manage_members") is False


def test_viewer_is_read_only():
	# viewer can read
	assert role_has_permission("viewer", "projects.read") is True
	assert role_has_permission("viewer", "episodes.read") is True
	# viewer cannot write
	assert role_has_permission("viewer", "projects.create") is False
	assert role_has_permission("viewer", "episodes.create") is False
	assert role_has_permission("viewer", "projects.edit") is False
	assert role_has_permission("viewer", "episodes.delete") is False


def test_analyst_can_view_analytics():
	assert role_has_permission("analyst", "analytics.view") is True
	assert role_has_permission("analyst", "analytics.export") is True


def test_analyst_cannot_create_projects():
	assert role_has_permission("analyst", "projects.create") is False


def test_unknown_role_returns_false():
	assert role_has_permission("superadmin", "projects.create") is False
	assert role_has_permission("", "team.delete") is False


def test_unknown_permission_returns_false():
	assert role_has_permission("owner", "nonexistent.permission") is False


def test_all_defined_roles_present():
	expected_roles = {"owner", "editor", "viewer", "analyst"}
	assert set(ROLE_PERMISSIONS.keys()) == expected_roles


def test_owner_can_delete_team():
	assert role_has_permission("owner", "team.delete") is True


def test_non_owner_cannot_delete_team():
	for role in ["editor", "viewer", "analyst"]:
		assert role_has_permission(role, "team.delete") is False


def test_owner_can_manage_billing():
	assert role_has_permission("owner", "billing.manage") is True


def test_non_owner_cannot_manage_billing():
	for role in ["editor", "viewer", "analyst"]:
		assert role_has_permission(role, "billing.manage") is False
