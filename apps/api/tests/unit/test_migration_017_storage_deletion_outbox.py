"""
Unit tests for migration 017_add_storage_deletion_outbox (issue #366).

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() creates the table, its index, and grants the app role
- downgrade() drops the table
"""

import importlib.util
import os
from unittest.mock import patch


def _load_migration():
	migration_path = os.path.join(
		os.path.dirname(__file__),
		'..', '..', 'alembic', 'versions',
		'017_add_storage_deletion_outbox.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_017', migration_path
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	"""Migration must declare revision ID '017'."""
	mod = _load_migration()
	assert mod.revision == '017'


def test_migration_down_revision():
	"""Migration must chain onto revision '016'."""
	mod = _load_migration()
	assert mod.down_revision == '016'


def test_migration_branch_labels_none():
	mod = _load_migration()
	assert mod.branch_labels is None


def test_migration_depends_on_none():
	mod = _load_migration()
	assert mod.depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_creates_storage_deletion_outbox_table():
	"""upgrade() must create the storage_deletion_outbox table."""
	mod = _load_migration()
	with patch('alembic.op.create_table') as mock_create_table, \
		patch('alembic.op.create_index'), \
		patch('alembic.op.execute'):
		mod.upgrade()
	table_names = [c.args[0] for c in mock_create_table.call_args_list]
	assert 'storage_deletion_outbox' in table_names


def test_upgrade_table_has_check_constraint_for_s3_key_or_file_path():
	"""The table must include a CHECK that s3_key or file_path is set."""
	mod = _load_migration()
	with patch('alembic.op.create_table') as mock_create_table, \
		patch('alembic.op.create_index'), \
		patch('alembic.op.execute'):
		mod.upgrade()
	call = mock_create_table.call_args_list[0]
	# CheckConstraint objects are passed as positional args alongside Columns.
	from sqlalchemy import CheckConstraint
	constraints = [arg for arg in call.args if isinstance(arg, CheckConstraint)]
	assert len(constraints) == 1


def test_upgrade_creates_created_at_index():
	"""upgrade() must create an index on created_at for the drain query."""
	mod = _load_migration()
	with patch('alembic.op.create_table'), \
		patch('alembic.op.create_index') as mock_create_index, \
		patch('alembic.op.execute'):
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create_index.call_args_list]
	assert 'ix_storage_deletion_outbox_created_at' in index_names


def test_upgrade_grants_app_role():
	"""upgrade() must GRANT the podcastfy_app role access to the table."""
	mod = _load_migration()
	with patch('alembic.op.create_table'), \
		patch('alembic.op.create_index'), \
		patch('alembic.op.execute') as mock_execute:
		mod.upgrade()
	statements = [c.args[0] for c in mock_execute.call_args_list]
	assert any(
		'GRANT' in s and 'storage_deletion_outbox' in s and 'podcastfy_app' in s
		for s in statements
	)


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_storage_deletion_outbox_table():
	mod = _load_migration()
	with patch('alembic.op.drop_table') as mock_drop:
		mod.downgrade()
	table_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'storage_deletion_outbox' in table_names
