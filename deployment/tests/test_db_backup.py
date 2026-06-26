"""Tests for the PostgreSQL backup/restore tooling (issue #293).

All durable tenant state lives only in the single VPS Postgres datadir. These
tests pin the disaster-recovery contract: an automated off-host nightly logical
dump to object storage with retention (installed via a systemd timer running as
the non-root service account), and a documented, tested restore runbook with
target RTO/RPO. They read the scripts statically — like test_deploy_hardening.py
— so a regression (dropping the S3 upload, the prune, or the restore guard)
fails CI without needing a live Postgres/S3.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "deployment" / "scripts"
BACKUP = SCRIPTS / "backup-db.sh"
INSTALL_TIMER = SCRIPTS / "install-db-backup-timer.sh"
RESTORE = SCRIPTS / "restore-db.sh"
README = REPO_ROOT / "deployment" / "README.md"


# ── Scripts exist and are executable ───────────────────────────────────────


def test_backup_scripts_exist_and_executable():
	for script in (BACKUP, INSTALL_TIMER, RESTORE):
		assert script.is_file(), f"expected script at {script}"
		assert script.stat().st_mode & 0o111, f"{script.name} must be executable"


def test_scripts_fail_fast():
	for script in (BACKUP, INSTALL_TIMER, RESTORE):
		assert "set -euo pipefail" in script.read_text(), (
			f"{script.name} must use 'set -euo pipefail'"
		)


# ── AC1: nightly logical dump, off-host to object storage, with retention ──


def test_backup_takes_logical_dump():
	text = BACKUP.read_text()
	assert "pg_dump" in text, "backup must take a logical dump with pg_dump"


def test_backup_uploads_off_host_to_s3():
	text = BACKUP.read_text()
	assert "aws s3" in text, "backup must upload off-host to S3 object storage"
	# Off-host is the whole point: a purely local dump is not a backup.
	assert "s3://" in text, "backup must write to an s3:// destination"


def test_backup_enforces_retention():
	text = BACKUP.read_text()
	assert "RETENTION" in text, "backup must honour a retention window"
	# Old backups must actually be pruned from object storage, not just locally.
	assert re.search(r"aws s3(api)?\s+(rm|delete-object)", text), (
		"backup must prune aged-out objects from S3"
	)


def test_backup_bucket_is_configurable():
	text = BACKUP.read_text()
	assert "DB_BACKUP_S3_BUCKET" in text, "backup bucket must be configurable"


# ── AC1: installed via a systemd timer running as the service account ──────


def test_install_timer_creates_systemd_timer():
	text = INSTALL_TIMER.read_text()
	assert ".timer" in text, "installer must create a systemd timer"
	assert ".service" in text, "installer must create a systemd service unit"
	assert re.search(r"OnCalendar=", text), "timer must schedule via OnCalendar"
	assert "systemctl" in text and "enable" in text, "installer must enable the timer"


def test_timer_runs_as_nonroot_service_account():
	text = INSTALL_TIMER.read_text()
	# The backup runs unattended; it must not run as root. Match the hardening
	# convention's dedicated 'podcastfy' service account.
	assert "podcastfy" in text or "SERVICE_USER" in text, (
		"backup timer must run as the non-root service account"
	)
	assert re.search(r"User=", text), "service unit must set User= to drop privileges"


# ── AC2: restore path ──────────────────────────────────────────────────────


def test_restore_uses_pg_restore_and_pulls_from_s3():
	text = RESTORE.read_text()
	assert "pg_restore" in text, "restore must use pg_restore on the custom-format dump"
	assert "aws s3" in text, "restore must fetch the dump from S3"


def test_restore_guards_against_accidental_clobber():
	text = RESTORE.read_text()
	# Restoring overwrites a live database — there must be a confirmation guard.
	assert re.search(r"(CONFIRM|--force|read -r|yes/no|[Aa]re you sure)", text), (
		"restore must guard against accidentally clobbering a live database"
	)


# ── AC2: documented runbook with RTO/RPO ───────────────────────────────────


def test_readme_documents_backup_and_restore_runbook():
	text = README.read_text()
	assert "backup-db.sh" in text, "README must reference the backup script"
	assert "restore-db.sh" in text, "README must reference the restore script"
	assert "install-db-backup-timer.sh" in text, "README must document timer install"


def test_readme_states_rto_and_rpo_targets():
	text = README.read_text().upper()
	assert "RTO" in text, "runbook must state a target RTO"
	assert "RPO" in text, "runbook must state a target RPO"
