"""Tests for DR/durability hardening (issue #319).

Pins three contracts on top of the #293 backup tooling:
1. The automated deploy takes a fresh off-host pg_dump BEFORE running
   `alembic upgrade head` on the live DB, and a dump failure aborts the deploy.
2. Redis durability is decided and actionable: an idempotent script enables
   AOF persistence, and the README documents the stance (AOF + stuck-job
   reaper backstop, what a flush loses).
3. S3 DR is documented: MFA-delete hardening and an object-restore runbook
   (versioned recovery) with stated RTO/RPO.

Static reads only, like test_db_backup.py — no live server/Redis/S3 needed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-dev.yml"
REDIS_SCRIPT = REPO_ROOT / "deployment" / "scripts" / "configure-redis-persistence.sh"
README = REPO_ROOT / "deployment" / "README.md"


# ── AC1: pre-migration off-host dump gates the deploy ──────────────────────


def _server_deploy_block() -> str:
	"""The server-side SSH block of the Deploy API step (after the rsyncs)."""
	text = DEPLOY_WORKFLOW.read_text()
	match = re.search(r"Install dependencies and restart on server(.*?)\n      - name:", text, re.S)
	assert match, "expected the server-side SSH deploy block in deploy-dev.yml"
	return match.group(1)


def test_deploy_dumps_before_migrating():
	block = _server_deploy_block()
	# Match the actual invocation, not prose in comments that mentions the script.
	dump = re.search(r"bash .*backup-db\.sh", block)
	migrate = re.search(r"uv run alembic upgrade head", block)
	assert dump, "server-side deploy must run backup-db.sh (pre-migration dump)"
	assert migrate, "server-side deploy must still run migrations"
	assert dump.start() < migrate.start(), (
		"the pre-migration dump must run BEFORE alembic upgrade head"
	)


def test_deploy_block_fails_fast_so_dump_gates_migration():
	# `set -e` is what turns a failed dump into an aborted deploy.
	assert "set -e" in _server_deploy_block(), "SSH deploy block must fail fast (set -e)"


def test_deploy_syncs_backup_script_to_server():
	text = DEPLOY_WORKFLOW.read_text()
	assert re.search(r"rsync.*\n?.*backup-db\.sh", text), (
		"deploy must rsync backup-db.sh to the server so the dump step can run"
	)


def test_pre_migration_dumps_use_dedicated_prefix():
	# A separate self-pruning prefix keeps "restore to just before the deploy"
	# distinguishable from the nightly dumps.
	assert "pre-migration" in DEPLOY_WORKFLOW.read_text(), (
		"pre-migration dumps must land under a dedicated S3 prefix"
	)


def test_backup_dumps_with_privileged_role():
	# Tenant tables are FORCE RLS (migration 014); a dump as the RLS-subject
	# app role errors or silently omits tenant rows. The backup must prefer
	# the BYPASSRLS migration role.
	backup = REPO_ROOT / "deployment" / "scripts" / "backup-db.sh"
	assert re.search(r"MIGRATION_DATABASE_URL[}:]", backup.read_text()), (
		"backup-db.sh must prefer MIGRATION_DATABASE_URL so RLS doesn't truncate dumps"
	)


def test_manual_deploy_runbook_includes_pre_migration_dump():
	text = README.read_text()
	dump = text.find("backup-db.sh", text.find("Step 2: Deploy API"))
	migrate = text.find("alembic upgrade head", text.find("Step 2: Deploy API"))
	assert dump != -1 and migrate != -1 and dump < migrate, (
		"manual deploy runbook must take a pre-migration dump before migrating"
	)


# ── AC2: Redis durability — AOF script + documented stance ─────────────────


def test_redis_persistence_script_exists_and_executable():
	assert REDIS_SCRIPT.is_file(), f"expected script at {REDIS_SCRIPT}"
	assert REDIS_SCRIPT.stat().st_mode & 0o111, "script must be executable"


def test_redis_persistence_script_fails_fast():
	assert "set -euo pipefail" in REDIS_SCRIPT.read_text()


def test_redis_persistence_script_enables_aof_durably():
	text = REDIS_SCRIPT.read_text()
	assert "appendonly" in text, "script must enable AOF (appendonly)"
	assert "appendfsync" in text, "script must pin the fsync policy"
	# CONFIG SET alone is lost on restart — it must persist to redis.conf.
	assert re.search(r"CONFIG\s+REWRITE", text, re.I), (
		"script must CONFIG REWRITE so AOF survives a redis restart"
	)


def test_redis_persistence_script_verifies_readback():
	# Trust but verify: the script must read the setting back, not assume it.
	assert re.search(r"CONFIG\s+GET\s+appendonly", REDIS_SCRIPT.read_text(), re.I)


def test_readme_documents_redis_durability_stance():
	text = README.read_text()
	assert "Redis durability" in text, "README must have a Redis durability section"
	assert "appendonly" in text or "AOF" in text, "README must document AOF"
	assert "reap_stuck_episodes" in text, (
		"README must document the stuck-job reaper as the backstop"
	)
	assert "configure-redis-persistence.sh" in text, (
		"README must reference the enable script"
	)


# ── AC3/AC4: S3 versioning hardening + restore runbook ─────────────────────


def test_readme_documents_mfa_delete():
	assert "MFA" in README.read_text(), (
		"README must document MFA-delete as S3 versioning hardening"
	)


def test_readme_has_s3_object_restore_runbook():
	text = README.read_text()
	assert "list-object-versions" in text, (
		"S3 restore runbook must show how to find prior versions"
	)
	assert "delete marker" in text.lower(), (
		"S3 restore runbook must cover recovering a deleted object (delete marker)"
	)


def test_readme_states_s3_rto_rpo():
	# The Postgres runbook already states RTO/RPO; the S3 section needs its own.
	text = README.read_text()
	s3_restore = text.find("list-object-versions")
	assert s3_restore != -1
	window = text[s3_restore - 2000 : s3_restore + 2000].upper()
	assert "RPO" in window and "RTO" in window, (
		"S3 restore runbook must state its RTO/RPO"
	)
