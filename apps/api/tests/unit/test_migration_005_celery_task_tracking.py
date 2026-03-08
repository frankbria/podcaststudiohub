"""
Unit tests for migration 005_add_celery_task_tracking.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() adds three new columns to episodes table
- upgrade() creates the task_id index
- downgrade() drops the index and columns in correct order
- Column types and nullability match specifications
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
		'005_add_celery_task_tracking.py',
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

def test_upgrade_adds_task_id_column():
	"""upgrade() must add task_id column to episodes table."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	table_col_pairs = [(c.args[0], c.args[1].name) for c in mock_add.call_args_list]
	assert ('episodes', 'task_id') in table_col_pairs


def test_upgrade_adds_task_started_at_column():
	"""upgrade() must add task_started_at column to episodes table."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	table_col_pairs = [(c.args[0], c.args[1].name) for c in mock_add.call_args_list]
	assert ('episodes', 'task_started_at') in table_col_pairs


def test_upgrade_adds_task_completed_at_column():
	"""upgrade() must add task_completed_at column to episodes table."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	table_col_pairs = [(c.args[0], c.args[1].name) for c in mock_add.call_args_list]
	assert ('episodes', 'task_completed_at') in table_col_pairs


def test_upgrade_adds_exactly_three_columns():
	"""upgrade() must add exactly three columns."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	assert mock_add.call_count == 3


def test_upgrade_creates_task_id_index():
	"""upgrade() must create idx_episodes_task_id index."""
	mod = _load_migration()
	with patch('alembic.op.add_column'), \
	     patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create.call_args_list]
	assert 'idx_episodes_task_id' in index_names


def test_upgrade_task_id_index_targets_correct_table_and_column():
	"""idx_episodes_task_id must target episodes.task_id."""
	mod = _load_migration()
	with patch('alembic.op.add_column'), \
	     patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_episodes_task_id']
	assert idx_call.args[1] == 'episodes'
	assert 'task_id' in idx_call.args[2]


def test_upgrade_task_id_column_is_nullable():
	"""task_id column must be nullable=True."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	calls_by_col = {c.args[1].name: c.args[1] for c in mock_add.call_args_list}
	assert calls_by_col['task_id'].nullable is True


def test_upgrade_task_started_at_column_is_nullable():
	"""task_started_at column must be nullable=True."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	calls_by_col = {c.args[1].name: c.args[1] for c in mock_add.call_args_list}
	assert calls_by_col['task_started_at'].nullable is True


def test_upgrade_task_completed_at_column_is_nullable():
	"""task_completed_at column must be nullable=True."""
	mod = _load_migration()
	with patch('alembic.op.add_column') as mock_add, \
	     patch('alembic.op.create_index'):
		mod.upgrade()
	calls_by_col = {c.args[1].name: c.args[1] for c in mock_add.call_args_list}
	assert calls_by_col['task_completed_at'].nullable is True


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_task_id_index():
	"""downgrade() must drop idx_episodes_task_id."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop, \
	     patch('alembic.op.drop_column'):
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'idx_episodes_task_id' in index_names


def test_downgrade_drops_task_id_column():
	"""downgrade() must drop task_id column from episodes."""
	mod = _load_migration()
	with patch('alembic.op.drop_index'), \
	     patch('alembic.op.drop_column') as mock_drop:
		mod.downgrade()
	table_col_pairs = [(c.args[0], c.args[1]) for c in mock_drop.call_args_list]
	assert ('episodes', 'task_id') in table_col_pairs


def test_downgrade_drops_task_started_at_column():
	"""downgrade() must drop task_started_at column from episodes."""
	mod = _load_migration()
	with patch('alembic.op.drop_index'), \
	     patch('alembic.op.drop_column') as mock_drop:
		mod.downgrade()
	table_col_pairs = [(c.args[0], c.args[1]) for c in mock_drop.call_args_list]
	assert ('episodes', 'task_started_at') in table_col_pairs


def test_downgrade_drops_task_completed_at_column():
	"""downgrade() must drop task_completed_at column from episodes."""
	mod = _load_migration()
	with patch('alembic.op.drop_index'), \
	     patch('alembic.op.drop_column') as mock_drop:
		mod.downgrade()
	table_col_pairs = [(c.args[0], c.args[1]) for c in mock_drop.call_args_list]
	assert ('episodes', 'task_completed_at') in table_col_pairs


def test_downgrade_drops_exactly_three_columns():
	"""downgrade() must drop exactly three columns."""
	mod = _load_migration()
	with patch('alembic.op.drop_index'), \
	     patch('alembic.op.drop_column') as mock_drop:
		mod.downgrade()
	assert mock_drop.call_count == 3


def test_downgrade_drops_exactly_one_index():
	"""downgrade() must drop exactly one index."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop, \
	     patch('alembic.op.drop_column'):
		mod.downgrade()
	assert mock_drop.call_count == 1
