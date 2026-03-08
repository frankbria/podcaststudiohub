"""
Unit tests for migration 006_make_episode_number_not_null.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() backfills NULLs, alters column, creates unique constraint and index
- downgrade() reverses all changes in correct order
"""

import importlib.util
import os
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helper: load the migration module by path so it doesn't need to be on
# sys.path and doesn't trigger alembic env initialisation.
# ---------------------------------------------------------------------------

def _load_migration():
	migration_path = os.path.join(
		os.path.dirname(__file__),
		'..', '..', 'alembic', 'versions',
		'006_make_episode_number_not_null.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_006', migration_path
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	"""Migration must declare revision ID '006'."""
	mod = _load_migration()
	assert mod.revision == '006'


def test_migration_down_revision():
	"""Migration must chain onto revision '005'."""
	mod = _load_migration()
	assert mod.down_revision == '005'


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

def test_upgrade_alters_column_not_null():
	"""upgrade() must alter episode_number to NOT NULL."""
	mod = _load_migration()
	mock_conn = MagicMock()
	with patch('alembic.op.get_bind', return_value=mock_conn), \
	     patch('alembic.op.alter_column') as mock_alter, \
	     patch('alembic.op.create_unique_constraint'), \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	# alter_column must be called for episodes.episode_number with nullable=False
	assert mock_alter.call_count >= 1
	alter_calls = {c.args[0]: c for c in mock_alter.call_args_list}
	assert 'episodes' in alter_calls
	episodes_call = alter_calls['episodes']
	assert episodes_call.args[1] == 'episode_number'
	assert episodes_call.kwargs.get('nullable') is False


def test_upgrade_creates_unique_constraint():
	"""upgrade() must create uq_episodes_project_number constraint."""
	mod = _load_migration()
	mock_conn = MagicMock()
	with patch('alembic.op.get_bind', return_value=mock_conn), \
	     patch('alembic.op.alter_column'), \
	     patch('alembic.op.create_unique_constraint') as mock_unique, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	constraint_names = [c.args[0] for c in mock_unique.call_args_list]
	assert 'uq_episodes_project_number' in constraint_names


def test_upgrade_unique_constraint_targets_correct_columns():
	"""uq_episodes_project_number must cover (project_id, episode_number)."""
	mod = _load_migration()
	mock_conn = MagicMock()
	with patch('alembic.op.get_bind', return_value=mock_conn), \
	     patch('alembic.op.alter_column'), \
	     patch('alembic.op.create_unique_constraint') as mock_unique, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_unique.call_args_list}
	uq_call = calls_by_name['uq_episodes_project_number']
	# args: (name, table, columns)
	assert uq_call.args[1] == 'episodes'
	columns = uq_call.args[2]
	assert 'project_id' in columns
	assert 'episode_number' in columns


def test_upgrade_creates_composite_index():
	"""upgrade() must create idx_episodes_project_number index."""
	mod = _load_migration()
	mock_conn = MagicMock()
	with patch('alembic.op.get_bind', return_value=mock_conn), \
	     patch('alembic.op.alter_column'), \
	     patch('alembic.op.create_unique_constraint'), \
	     patch('alembic.op.create_index') as mock_idx:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_idx.call_args_list]
	assert 'idx_episodes_project_number' in index_names


def test_upgrade_index_targets_correct_table_and_columns():
	"""idx_episodes_project_number must target episodes.(project_id, episode_number)."""
	mod = _load_migration()
	mock_conn = MagicMock()
	with patch('alembic.op.get_bind', return_value=mock_conn), \
	     patch('alembic.op.alter_column'), \
	     patch('alembic.op.create_unique_constraint'), \
	     patch('alembic.op.create_index') as mock_idx:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_idx.call_args_list}
	idx_call = calls_by_name['idx_episodes_project_number']
	assert idx_call.args[1] == 'episodes'
	columns = idx_call.args[2]
	assert 'project_id' in columns
	assert 'episode_number' in columns


def test_upgrade_executes_backfill_sql():
	"""upgrade() must execute a SQL statement to backfill NULL episode_numbers."""
	mod = _load_migration()
	mock_conn = MagicMock()
	with patch('alembic.op.get_bind', return_value=mock_conn), \
	     patch('alembic.op.alter_column'), \
	     patch('alembic.op.create_unique_constraint'), \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	assert mock_conn.execute.called


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_index():
	"""downgrade() must drop idx_episodes_project_number."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop_idx, \
	     patch('alembic.op.drop_constraint'), \
	     patch('alembic.op.alter_column'):
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop_idx.call_args_list]
	assert 'idx_episodes_project_number' in index_names


def test_downgrade_drops_unique_constraint():
	"""downgrade() must drop uq_episodes_project_number."""
	mod = _load_migration()
	with patch('alembic.op.drop_index'), \
	     patch('alembic.op.drop_constraint') as mock_drop_con, \
	     patch('alembic.op.alter_column'):
		mod.downgrade()
	constraint_names = [c.args[0] for c in mock_drop_con.call_args_list]
	assert 'uq_episodes_project_number' in constraint_names


def test_downgrade_restores_nullable_column():
	"""downgrade() must alter episode_number back to nullable."""
	mod = _load_migration()
	with patch('alembic.op.drop_index'), \
	     patch('alembic.op.drop_constraint'), \
	     patch('alembic.op.alter_column') as mock_alter:
		mod.downgrade()
	assert mock_alter.call_count >= 1
	alter_calls = {c.args[0]: c for c in mock_alter.call_args_list}
	assert 'episodes' in alter_calls
	episodes_call = alter_calls['episodes']
	assert episodes_call.args[1] == 'episode_number'
	assert episodes_call.kwargs.get('nullable') is True
