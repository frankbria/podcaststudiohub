"""
Unit tests for migration 005_add_fk_indexes.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() creates the missing layout_id index with correct name and column,
  CONCURRENTLY inside an autocommit block (issue #318 — no write-blocking locks)
- upgrade() emits a DROP INDEX IF EXISTS rerun guard
- downgrade() drops the index
- Index name follows project convention: idx_{table}_{column}
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
		'005_add_fk_indexes.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_005', migration_path
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _run_upgrade():
	"""Run upgrade() with alembic entry points mocked.

	Returns (mock_create_index, executed_sql, mock_context).
	"""
	executed = []
	ctx = MagicMock()
	with patch('alembic.op.create_index') as mock_create, \
	     patch('alembic.op.execute', side_effect=lambda s, *a, **k: executed.append(str(s))), \
	     patch('alembic.op.get_context', return_value=ctx):
		_load_migration().upgrade()
	return mock_create, executed, ctx


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	"""Migration must declare revision ID '005'."""
	assert _load_migration().revision == '005'


def test_migration_down_revision():
	"""Migration must chain onto revision '004'."""
	assert _load_migration().down_revision == '004'


def test_migration_branch_labels_none():
	"""Migration must not declare any branch labels."""
	assert _load_migration().branch_labels is None


def test_migration_depends_on_none():
	"""Migration must not declare any cross-branch dependencies."""
	assert _load_migration().depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_creates_layout_id_index_on_correct_column():
	"""upgrade() must create exactly idx_episode_compositions_layout_id."""
	mock_create, _, _ = _run_upgrade()
	assert mock_create.call_count == 1
	idx_call = mock_create.call_args_list[0]
	assert idx_call.args[0] == 'idx_episode_compositions_layout_id'
	assert idx_call.args[1] == 'episode_compositions'
	assert 'layout_id' in idx_call.args[2]


def test_upgrade_creates_index_concurrently():
	"""episode_compositions pre-exists and may be large; build CONCURRENTLY (#318)."""
	mock_create, _, _ = _run_upgrade()
	idx_call = mock_create.call_args_list[0]
	assert idx_call.kwargs.get('postgresql_concurrently') is True


def test_upgrade_runs_inside_autocommit_block():
	"""CONCURRENTLY cannot run in a transaction; an autocommit block is required."""
	_, _, ctx = _run_upgrade()
	assert ctx.autocommit_block.called


def test_upgrade_emits_rerun_guard():
	"""A DROP INDEX IF EXISTS guard makes reruns safe after a failed
	CONCURRENTLY build (which leaves an INVALID index)."""
	_, executed, _ = _run_upgrade()
	assert any(
		"drop index if exists idx_episode_compositions_layout_id" in s.lower()
		for s in executed
	)


def test_upgrade_layout_id_uses_btree():
	"""idx_episode_compositions_layout_id must use btree index type."""
	mock_create, _, _ = _run_upgrade()
	idx_call = mock_create.call_args_list[0]
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
