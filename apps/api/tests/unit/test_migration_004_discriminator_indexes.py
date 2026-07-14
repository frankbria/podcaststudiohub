"""
Unit tests for migration 004_add_missing_discriminator_indexes.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() creates all four missing indexes with correct names and columns,
  CONCURRENTLY inside an autocommit block (issue #318 — no write-blocking locks)
- upgrade() emits DROP INDEX IF EXISTS rerun guards (failed CONCURRENTLY
  builds leave INVALID indexes behind)
- downgrade() drops all four indexes
- Index names follow project convention: idx_{table}_{column}
"""

import importlib.util
import os
from unittest.mock import patch, MagicMock


EXPECTED_INDEXES = {
	'idx_content_sources_source_type': ('content_sources', 'source_type'),
	'idx_content_sources_extraction_status': ('content_sources', 'extraction_status'),
	'idx_distribution_targets_target_type': ('distribution_targets', 'target_type'),
	'idx_tts_configurations_provider': ('tts_configurations', 'provider'),
}


# ---------------------------------------------------------------------------
# Helper: load the migration module by path so it doesn't need to be on
# sys.path and doesn't trigger alembic env initialisation.
# ---------------------------------------------------------------------------

def _load_migration():
	migration_path = os.path.join(
		os.path.dirname(__file__),
		'..', '..', 'alembic', 'versions',
		'004_add_missing_discriminator_indexes.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_004', migration_path
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
	"""Migration must declare revision ID '004'."""
	assert _load_migration().revision == '004'


def test_migration_down_revision():
	"""Migration must chain onto revision '003'."""
	assert _load_migration().down_revision == '003'


def test_migration_branch_labels_none():
	"""Migration must not declare any branch labels."""
	assert _load_migration().branch_labels is None


def test_migration_depends_on_none():
	"""Migration must not declare any cross-branch dependencies."""
	assert _load_migration().depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_creates_all_four_indexes_on_correct_columns():
	"""upgrade() must create exactly the four expected indexes."""
	mock_create, _, _ = _run_upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	assert set(calls_by_name) == set(EXPECTED_INDEXES)
	for name, (table, column) in EXPECTED_INDEXES.items():
		idx_call = calls_by_name[name]
		assert idx_call.args[1] == table
		assert column in idx_call.args[2]


def test_upgrade_creates_indexes_concurrently():
	"""All indexes target pre-existing tables and must build CONCURRENTLY (#318)."""
	mock_create, _, _ = _run_upgrade()
	for c in mock_create.call_args_list:
		assert c.kwargs.get('postgresql_concurrently') is True, (
			f"{c.args[0]} not created CONCURRENTLY"
		)


def test_upgrade_runs_inside_autocommit_block():
	"""CONCURRENTLY cannot run in a transaction; an autocommit block is required."""
	_, _, ctx = _run_upgrade()
	assert ctx.autocommit_block.called


def test_upgrade_emits_rerun_guards():
	"""Each index needs a DROP INDEX IF EXISTS guard so a failed CONCURRENTLY
	build (which leaves an INVALID index) doesn't wedge the migration."""
	_, executed, _ = _run_upgrade()
	lowered = " ".join(executed).lower()
	for name in EXPECTED_INDEXES:
		assert f"drop index if exists {name}" in lowered, f"missing guard for {name}"


def test_upgrade_indexes_use_btree():
	"""Indexes must use btree."""
	mock_create, _, _ = _run_upgrade()
	for c in mock_create.call_args_list:
		assert c.kwargs.get('postgresql_using') == 'btree'


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_all_four_indexes():
	"""downgrade() must drop exactly the four indexes."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert set(index_names) == set(EXPECTED_INDEXES)
	assert mock_drop.call_count == 4
