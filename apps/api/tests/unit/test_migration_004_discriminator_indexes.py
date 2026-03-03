"""
Unit tests for migration 004_add_missing_discriminator_indexes.

Tests cover:
- Migration metadata (revision ID, down_revision chaining)
- upgrade() creates all four missing indexes with correct names and columns
- downgrade() drops all four indexes
- Index names follow project convention: idx_{table}_{column}
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
		'004_add_missing_discriminator_indexes.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location(
		'migration_004', migration_path
	)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	"""Migration must declare revision ID '004'."""
	mod = _load_migration()
	assert mod.revision == '004'


def test_migration_down_revision():
	"""Migration must chain onto revision '003'."""
	mod = _load_migration()
	assert mod.down_revision == '003'


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

def test_upgrade_creates_content_sources_source_type_index():
	"""upgrade() must create idx_content_sources_source_type."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create.call_args_list]
	assert 'idx_content_sources_source_type' in index_names


def test_upgrade_creates_content_sources_extraction_status_index():
	"""upgrade() must create idx_content_sources_extraction_status."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create.call_args_list]
	assert 'idx_content_sources_extraction_status' in index_names


def test_upgrade_creates_distribution_targets_target_type_index():
	"""upgrade() must create idx_distribution_targets_target_type."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create.call_args_list]
	assert 'idx_distribution_targets_target_type' in index_names


def test_upgrade_creates_tts_configurations_provider_index():
	"""upgrade() must create idx_tts_configurations_provider."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	index_names = [c.args[0] for c in mock_create.call_args_list]
	assert 'idx_tts_configurations_provider' in index_names


def test_upgrade_creates_exactly_four_indexes():
	"""upgrade() must create exactly four indexes."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	assert mock_create.call_count == 4


def test_upgrade_source_type_targets_correct_table_and_column():
	"""idx_content_sources_source_type must target content_sources.source_type."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_content_sources_source_type']
	# args: (index_name, table_name, columns, ...)
	assert idx_call.args[1] == 'content_sources'
	assert 'source_type' in idx_call.args[2]


def test_upgrade_extraction_status_targets_correct_table_and_column():
	"""idx_content_sources_extraction_status must target content_sources.extraction_status."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_content_sources_extraction_status']
	assert idx_call.args[1] == 'content_sources'
	assert 'extraction_status' in idx_call.args[2]


def test_upgrade_target_type_targets_correct_table_and_column():
	"""idx_distribution_targets_target_type must target distribution_targets.target_type."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_distribution_targets_target_type']
	assert idx_call.args[1] == 'distribution_targets'
	assert 'target_type' in idx_call.args[2]


def test_upgrade_provider_targets_correct_table_and_column():
	"""idx_tts_configurations_provider must target tts_configurations.provider."""
	mod = _load_migration()
	with patch('alembic.op.create_index') as mock_create:
		mod.upgrade()
	calls_by_name = {c.args[0]: c for c in mock_create.call_args_list}
	idx_call = calls_by_name['idx_tts_configurations_provider']
	assert idx_call.args[1] == 'tts_configurations'
	assert 'provider' in idx_call.args[2]


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_content_sources_source_type_index():
	"""downgrade() must drop idx_content_sources_source_type."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'idx_content_sources_source_type' in index_names


def test_downgrade_drops_content_sources_extraction_status_index():
	"""downgrade() must drop idx_content_sources_extraction_status."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'idx_content_sources_extraction_status' in index_names


def test_downgrade_drops_distribution_targets_target_type_index():
	"""downgrade() must drop idx_distribution_targets_target_type."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'idx_distribution_targets_target_type' in index_names


def test_downgrade_drops_tts_configurations_provider_index():
	"""downgrade() must drop idx_tts_configurations_provider."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	index_names = [c.args[0] for c in mock_drop.call_args_list]
	assert 'idx_tts_configurations_provider' in index_names


def test_downgrade_drops_exactly_four_indexes():
	"""downgrade() must drop exactly four indexes."""
	mod = _load_migration()
	with patch('alembic.op.drop_index') as mock_drop:
		mod.downgrade()
	assert mock_drop.call_count == 4
