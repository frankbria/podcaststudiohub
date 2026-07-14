"""
Unit tests for migration 006_make_episode_number_not_null.

Tests cover (issue #318 hardening):
- Migration metadata (revision ID, down_revision chaining)
- upgrade() disables row_security before touching episodes (issue #301)
- upgrade() renumbers pre-existing (project_id, episode_number) duplicates
  BEFORE the NULL backfill, so the unique constraint can never abort
- upgrade() enforces NOT NULL via CHECK NOT VALID -> VALIDATE -> SET NOT NULL
  (no full-table scan under ACCESS EXCLUSIVE)
- upgrade() builds the unique index CONCURRENTLY, then attaches it as the
  uq_episodes_project_number constraint via USING INDEX
- upgrade() builds idx_episodes_project_number CONCURRENTLY
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


def _run_upgrade(mod):
	"""Run upgrade() with all alembic entry points mocked.

	Returns (sql_calls, mock_create_index) where sql_calls is the ordered list
	of SQL strings executed across BOTH paths (connection.execute via
	op.get_bind, and op.execute) so cross-stream ordering can be asserted.
	"""
	calls = []

	def rec_bind(stmt, *args, **kwargs):
		calls.append(str(stmt))
		return MagicMock()

	def rec_op(stmt, *args, **kwargs):
		calls.append(str(stmt))

	bind = MagicMock()
	bind.execute.side_effect = rec_bind
	with patch('alembic.op.get_bind', return_value=bind), \
	     patch('alembic.op.execute', side_effect=rec_op), \
	     patch('alembic.op.get_context', return_value=MagicMock()), \
	     patch('alembic.op.create_index') as mock_idx:
		mod.upgrade()
	return calls, mock_idx


# ============================================================================
# METADATA TESTS
# ============================================================================

def test_migration_revision_id():
	"""Migration must declare revision ID '006'."""
	assert _load_migration().revision == '006'


def test_migration_down_revision():
	"""Migration must chain onto revision '005'."""
	assert _load_migration().down_revision == '005'


def test_migration_branch_labels_none():
	assert _load_migration().branch_labels is None


def test_migration_depends_on_none():
	assert _load_migration().depends_on is None


# ============================================================================
# UPGRADE TESTS
# ============================================================================

def test_upgrade_disables_row_security_first():
	"""`SET LOCAL row_security = off` must precede all data access (issue #301)."""
	calls, _ = _run_upgrade(_load_migration())
	assert calls, "upgrade() executed no SQL"
	assert calls[0].strip().lower() == "set local row_security = off"


def test_upgrade_renumbers_duplicates_before_backfill():
	"""Pre-existing (project_id, episode_number) duplicates must be renumbered
	BEFORE the NULL backfill, otherwise the unique constraint aborts (#318)."""
	calls, _ = _run_upgrade(_load_migration())
	lowered = [c.lower() for c in calls]
	dedupe_idx = next(
		(i for i, c in enumerate(lowered) if "dup_rank" in c), None
	)
	backfill_idx = next(
		(i for i, c in enumerate(lowered) if "episode_number is null" in c), None
	)
	assert dedupe_idx is not None, "no duplicate-renumbering statement found"
	assert backfill_idx is not None, "no NULL backfill statement found"
	assert dedupe_idx < backfill_idx, "dedupe must run before the NULL backfill"


def test_upgrade_dedupe_keeps_earliest_and_renumbers_above_max():
	"""The dedupe statement must rank duplicates by created_at (keep earliest)
	and renumber losers above the project's current max episode_number."""
	calls, _ = _run_upgrade(_load_migration())
	dedupe = next(c for c in calls if "dup_rank" in c.lower())
	lowered = dedupe.lower()
	assert "partition by project_id, episode_number" in lowered
	assert "order by created_at asc" in lowered
	assert "max(episode_number)" in lowered


def test_upgrade_not_null_uses_not_valid_then_validate():
	"""NOT NULL must be applied via CHECK ... NOT VALID -> VALIDATE ->
	SET NOT NULL -> DROP CHECK, never a scanning ALTER under exclusive lock."""
	calls, _ = _run_upgrade(_load_migration())
	lowered = [c.lower() for c in calls]

	def idx_of(fragment):
		match = next((i for i, c in enumerate(lowered) if fragment in c), None)
		assert match is not None, f"missing statement containing: {fragment}"
		return match

	add_idx = idx_of("check (episode_number is not null) not valid")
	validate_idx = idx_of("validate constraint ck_episodes_episode_number_not_null")
	set_idx = idx_of("alter column episode_number set not null")
	drop_idx = idx_of("drop constraint ck_episodes_episode_number_not_null")
	assert add_idx < validate_idx < set_idx < drop_idx


def test_upgrade_check_constraint_add_has_rerun_guard():
	"""Everything before the autocommit block commits when it opens, so a
	later failure would strand the check constraint; the re-add must be
	preceded by DROP CONSTRAINT IF EXISTS to keep reruns safe (#318)."""
	calls, _ = _run_upgrade(_load_migration())
	lowered = [c.lower() for c in calls]
	guard_idx = next(
		(i for i, c in enumerate(lowered)
		 if "drop constraint if exists ck_episodes_episode_number_not_null" in c),
		None,
	)
	add_idx = next(
		i for i, c in enumerate(lowered)
		if "check (episode_number is not null) not valid" in c
	)
	assert guard_idx is not None, "missing DROP CONSTRAINT IF EXISTS rerun guard"
	assert guard_idx < add_idx


def test_upgrade_does_not_use_scanning_alter_column():
	"""upgrade() must not call op.alter_column (full-scan ACCESS EXCLUSIVE)."""
	mod = _load_migration()
	bind = MagicMock()
	with patch('alembic.op.get_bind', return_value=bind), \
	     patch('alembic.op.execute'), \
	     patch('alembic.op.get_context', return_value=MagicMock()), \
	     patch('alembic.op.create_index'), \
	     patch('alembic.op.alter_column') as mock_alter, \
	     patch('alembic.op.create_unique_constraint') as mock_uq:
		mod.upgrade()
	assert not mock_alter.called
	assert not mock_uq.called


def test_upgrade_builds_unique_index_concurrently_then_attaches():
	"""Unique enforcement must be CREATE UNIQUE INDEX CONCURRENTLY followed by
	ADD CONSTRAINT ... UNIQUE USING INDEX (no write-blocking index build)."""
	calls, _ = _run_upgrade(_load_migration())
	lowered = [c.lower() for c in calls]
	create_idx = next(
		(i for i, c in enumerate(lowered)
		 if "create unique index concurrently uq_episodes_project_number" in c),
		None,
	)
	attach_idx = next(
		(i for i, c in enumerate(lowered)
		 if "unique using index uq_episodes_project_number" in c),
		None,
	)
	assert create_idx is not None, "unique index not built CONCURRENTLY"
	assert attach_idx is not None, "unique index never attached as constraint"
	assert create_idx < attach_idx
	# Rerun-safety: a failed CONCURRENTLY build leaves an INVALID index behind.
	assert any(
		"drop index if exists uq_episodes_project_number" in c for c in lowered
	), "missing DROP INDEX IF EXISTS rerun guard"
	# Rerun-safety, post-attach window: once the constraint owns the index,
	# DROP INDEX alone errors — the constraint must be dropped first.
	con_guard_idx = next(
		(i for i, c in enumerate(lowered)
		 if "drop constraint if exists uq_episodes_project_number" in c),
		None,
	)
	assert con_guard_idx is not None, "missing DROP CONSTRAINT IF EXISTS rerun guard"
	assert con_guard_idx < create_idx


def test_upgrade_creates_composite_index_concurrently():
	"""idx_episodes_project_number must be created with CONCURRENTLY."""
	_, mock_idx = _run_upgrade(_load_migration())
	calls_by_name = {c.args[0]: c for c in mock_idx.call_args_list}
	assert 'idx_episodes_project_number' in calls_by_name
	idx_call = calls_by_name['idx_episodes_project_number']
	assert idx_call.args[1] == 'episodes'
	assert 'project_id' in idx_call.args[2]
	assert 'episode_number' in idx_call.args[2]
	assert idx_call.kwargs.get('postgresql_concurrently') is True


def test_upgrade_dedupe_and_backfill_precede_constraints():
	"""All data repair must be complete before any constraint DDL runs."""
	calls, _ = _run_upgrade(_load_migration())
	lowered = [c.lower() for c in calls]
	backfill_idx = next(
		i for i, c in enumerate(lowered) if "episode_number is null" in c
	)
	first_ddl_idx = next(
		i for i, c in enumerate(lowered) if "alter table episodes" in c
	)
	assert backfill_idx < first_ddl_idx


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
	alter_calls = {c.args[0]: c for c in mock_alter.call_args_list}
	assert 'episodes' in alter_calls
	episodes_call = alter_calls['episodes']
	assert episodes_call.args[1] == 'episode_number'
	assert episodes_call.kwargs.get('nullable') is True
