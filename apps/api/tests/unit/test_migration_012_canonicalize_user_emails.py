"""
Unit tests for migration 012_canonicalize_user_emails.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() disables row_security before touching users (issue #301)
- upgrade() aborts loudly on case-variant collisions (preserved behavior)
- upgrade() lowercases emails and creates the unique lower(email) index
- downgrade() drops the index
"""

import importlib.util
import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


def _load_migration():
	migration_path = os.path.join(
		os.path.dirname(__file__),
		'..', '..', 'alembic', 'versions',
		'012_canonicalize_user_emails.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_012', migration_path
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _bind_with_collisions(rows):
	"""Mock bind whose collision SELECT returns ``rows`` from .fetchall()."""
	bind = MagicMock()
	bind.execute.return_value.fetchall.return_value = rows
	return bind


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	assert _load_migration().revision == '012'


def test_migration_down_revision():
	assert _load_migration().down_revision == '011'


def test_migration_branch_labels_none():
	assert _load_migration().branch_labels is None


def test_migration_depends_on_none():
	assert _load_migration().depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_disables_row_security_first():
	"""upgrade() must `SET LOCAL row_security = off` before any table access (issue #301).

	Records SQL across BOTH execution paths (bind.execute for the collision SELECT,
	op.execute for the lowercase UPDATE) so the test proves the guard precedes the
	UPDATE — not merely that it precedes other bind.execute calls.
	"""
	mod = _load_migration()
	calls = []

	def rec_bind(stmt, *args, **kwargs):
		calls.append(str(stmt))
		result = MagicMock()
		result.fetchall.return_value = []  # no collisions
		return result

	def rec_op(stmt, *args, **kwargs):
		calls.append(str(stmt))

	bind = MagicMock()
	bind.execute.side_effect = rec_bind
	with patch('alembic.op.get_bind', return_value=bind), \
	     patch('alembic.op.execute', side_effect=rec_op), \
	     patch('alembic.op.create_index'):
		mod.upgrade()

	assert calls, "upgrade() executed no SQL"
	assert calls[0].strip().lower() == "set local row_security = off"
	lowered = [c.lower() for c in calls]
	guard_idx = next(i for i, c in enumerate(lowered) if "row_security" in c)
	update_idx = next(
		i for i, c in enumerate(lowered)
		if "update users set email = lower(email)" in c
	)
	assert guard_idx < update_idx, "row_security guard must precede the email UPDATE"


def test_upgrade_lowercases_and_creates_unique_index_when_clean():
	"""With no collisions, upgrade() lowercases emails and builds the unique index."""
	mod = _load_migration()
	bind = _bind_with_collisions([])
	with patch('alembic.op.get_bind', return_value=bind), \
	     patch('alembic.op.execute') as mock_exec, \
	     patch('alembic.op.create_index') as mock_idx:
		mod.upgrade()
	# op.execute carries the lowercase UPDATE.
	update_sql = " ".join(str(c.args[0]).lower() for c in mock_exec.call_args_list)
	assert "update users set email = lower(email)" in update_sql
	index_names = [c.args[0] for c in mock_idx.call_args_list]
	assert 'uq_users_email_lower' in index_names


def test_upgrade_aborts_on_case_variant_collision():
	"""upgrade() must raise RuntimeError when case-variant duplicates exist."""
	mod = _load_migration()
	bind = _bind_with_collisions([SimpleNamespace(canonical="a@x.com", n=2)])
	with patch('alembic.op.get_bind', return_value=bind), \
	     patch('alembic.op.execute') as mock_exec, \
	     patch('alembic.op.create_index') as mock_idx:
		with pytest.raises(RuntimeError, match="case-variant duplicate"):
			mod.upgrade()
	# Must abort before mutating data or creating the index.
	assert not mock_exec.called
	assert not mock_idx.called


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_index():
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop_idx:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop_idx.call_args_list]
	assert 'uq_users_email_lower' in index_names
