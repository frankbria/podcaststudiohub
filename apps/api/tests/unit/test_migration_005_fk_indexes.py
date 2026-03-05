"""
Unit tests for migration 005_add_fk_indexes.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() creates the missing layout_id index with correct name and column
- downgrade() drops the index
- Index name follows project convention: idx_{table}_{column}
"""

import importlib.util
import os
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper: load the migration module by path so it doesn't need to be on
# sys.path and doesn't trigger alembic env initialisation.
# ---------------------------------------------------------------------------

def _load_migration():
	migration_path = os.path.join(
		os.path.dirname(__file__),
		'..', '..', 'alembic', 'versions',
		'005_add_fk_indexes.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_005', migration_path
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	"""Migration must declare revision ID '005'."""
	mod = _load_migration()
	assert mod.revision == '005'


def test_migration_down_revision():
	"""Migration must chain onto revision '004'."""
	mod = _load_migration()
	assert mod.down_revision == '004'


def test_migration_branch_labels_none():
	"""Migration must not declare any branch labels."""
	mod = _load_migration()
	assert mod.branch_labels is None


def test_migration_depends_on_none():
	"""Migration must not declare any cross-branch dependencies."""
	mod = _load_migration()
	assert mod.depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_creates_episode_compositions_layout_id_index():
	"""upgrade() must create idx_episode_compositions_layout_id."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create.call_args_list]
	assert 'idx_episode_compositions_layout_id' in index_names


def test_upgrade_creates_exactly_one_index():
	"""upgrade() must create exactly one index."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	assert mock_create.call_count == 1


def test_upgrade_layout_id_targets_correct_table_and_column():
	"""idx_episode_compositions_layout_id must target episode_compositions.layout_id."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_episode_compositions_layout_id']
	# args: (index_name, table_name, columns, ...)
	assert idx_call.args[1] == 'episode_compositions'
	assert 'layout_id' in idx_call.args[2]


def test_upgrade_layout_id_uses_btree():
	"""idx_episode_compositions_layout_id must use btree index type."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_episode_compositions_layout_id']
	assert idx_call.kwargs.get('postgresql_using') == 'btree'


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_episode_compositions_layout_id_index():
	"""downgrade() must drop idx_episode_compositions_layout_id."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'idx_episode_compositions_layout_id' in index_names


def test_downgrade_drops_exactly_one_index():
	"""downgrade() must drop exactly one index."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	assert mock_drop.call_count == 1


def test_downgrade_drops_from_correct_table():
	"""downgrade() must drop the index from episode_compositions table."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	calls_by_name = {c.args[0]: c for c in mock_drop.call_args_list}
	idx_call = calls_by_name['idx_episode_compositions_layout_id']
	assert idx_call.kwargs.get('table_name') == 'episode_compositions'
