"""
Unit tests for migration 018_episode_search_indexes.

Tests cover:
- Migration metadata (revision ID '018', chains onto '017', no branch/deps)
- upgrade() enables pg_trgm and creates GIN gin_trgm_ops expression indexes on
  episode_metadata->>'title' and ->>'description', plus a btree on created_at
- All three indexes are built CONCURRENTLY inside an autocommit block (issue
  #318) with DROP INDEX IF EXISTS rerun guards
- downgrade() drops all three indexes (pg_trgm extension is intentionally kept)
"""

import importlib.util
import os
from unittest.mock import patch, MagicMock


def _load_migration():
	migration_path = os.path.join(
		os.path.dirname(__file__),
		'..', '..', 'alembic', 'versions',
		'018_episode_search_indexes.py',
	)
	migration_path = os.path.normpath(migration_path)
	spec = importlib.util.spec_from_file_location('migration_018', migration_path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _run_upgrade():
	"""Run upgrade() with alembic entry points mocked; return (executed_sql, ctx)."""
	executed = []
	ctx = MagicMock()
	with patch('alembic.op.execute', side_effect=lambda s, *a, **k: executed.append(str(s))), \
	     patch('alembic.op.get_context', return_value=ctx):
		_load_migration().upgrade()
	return executed, ctx


def _run_downgrade():
	executed = []
	ctx = MagicMock()
	with patch('alembic.op.execute', side_effect=lambda s, *a, **k: executed.append(str(s))), \
	     patch('alembic.op.get_context', return_value=ctx):
		_load_migration().downgrade()
	return executed, ctx


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	assert _load_migration().revision == '018'


def test_migration_down_revision():
	assert _load_migration().down_revision == '017'


def test_migration_branch_labels_none():
	assert _load_migration().branch_labels is None


def test_migration_depends_on_none():
	assert _load_migration().depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_enables_pg_trgm():
	executed, _ = _run_upgrade()
	assert any("create extension if not exists pg_trgm" in s.lower() for s in executed)


def test_upgrade_creates_title_trgm_gin_index():
	executed, _ = _run_upgrade()
	joined = " ".join(executed).lower()
	assert "using gin" in joined
	assert "gin_trgm_ops" in joined
	assert "episode_metadata->>'title'" in joined.replace(" ", "")


def test_upgrade_creates_description_trgm_gin_index():
	executed, _ = _run_upgrade()
	joined = " ".join(executed).lower().replace(" ", "")
	assert "episode_metadata->>'description'" in joined


def test_upgrade_creates_created_at_btree_index():
	executed, _ = _run_upgrade()
	joined = " ".join(executed).lower()
	assert "using btree" in joined
	assert "created_at" in joined


def test_upgrade_builds_indexes_concurrently():
	executed, _ = _run_upgrade()
	concurrent_creates = [s for s in executed if "create index concurrently" in s.lower()]
	# title + description + created_at
	assert len(concurrent_creates) == 3


def test_upgrade_runs_inside_autocommit_block():
	"""CONCURRENTLY cannot run in a transaction; an autocommit block is required."""
	_, ctx = _run_upgrade()
	assert ctx.autocommit_block.called


def test_upgrade_emits_rerun_guards():
	"""Each CONCURRENTLY create is preceded by a DROP INDEX IF EXISTS guard."""
	executed, _ = _run_upgrade()
	drop_guards = [s for s in executed if "drop index if exists" in s.lower()]
	assert len(drop_guards) == 3


# ============================================================================
# DOWNGRADE TESTS
# ============================================================================

def test_downgrade_drops_all_three_indexes():
	executed, _ = _run_downgrade()
	joined = " ".join(executed).lower()
	assert "idx_episodes_metadata_title_trgm" in joined
	assert "idx_episodes_metadata_description_trgm" in joined
	assert "idx_episodes_created_at" in joined


def test_downgrade_uses_if_exists_guards():
	executed, _ = _run_downgrade()
	drops = [s for s in executed if "drop index if exists" in s.lower()]
	assert len(drops) == 3
