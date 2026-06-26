#!/usr/bin/env bash
#
# Restore a PostgreSQL backup from S3 (issue #293) — the DR recovery path.
#
# Fetches a custom-format dump produced by backup-db.sh and pg_restore's it into
# the target database. Restoring OVERWRITES live data, so it requires explicit
# confirmation (or DB_RESTORE_FORCE=1 for unattended runs).
#
#   bash deployment/scripts/restore-db.sh                 # restore the latest backup
#   bash deployment/scripts/restore-db.sh <s3-key-or-name># restore a specific backup
#   DB_RESTORE_FORCE=1 bash deployment/scripts/restore-db.sh   # skip the prompt
#
# Configuration mirrors backup-db.sh:
#   DATABASE_URL / PG* libpq vars   target database
#   DB_BACKUP_S3_BUCKET (default $AWS_S3_BUCKET), DB_BACKUP_S3_PREFIX (db-backups/)
#   DB_RESTORE_FORCE=1              skip the confirmation prompt

set -euo pipefail

DB_BACKUP_S3_BUCKET="${DB_BACKUP_S3_BUCKET:-${AWS_S3_BUCKET:-}}"
DB_BACKUP_S3_PREFIX="${DB_BACKUP_S3_PREFIX:-db-backups/}"

if [[ -z "$DB_BACKUP_S3_BUCKET" ]]; then
	echo "DB_BACKUP_S3_BUCKET (or AWS_S3_BUCKET) must be set." >&2
	exit 1
fi

# pg_restore --dbname needs an explicit target. Prefer DATABASE_URL (normalised
# off any +asyncpg driver suffix); otherwise fall back to PGDATABASE so the
# remaining libpq PG* vars (host/user/password) still apply.
if [[ -n "${DATABASE_URL:-}" ]]; then
	TARGET_DB="${DATABASE_URL/postgresql+asyncpg:/postgresql:}"
	TARGET_DB="${TARGET_DB/postgres+asyncpg:/postgres:}"
elif [[ -n "${PGDATABASE:-}" ]]; then
	TARGET_DB="$PGDATABASE"
else
	echo "Set DATABASE_URL or PGDATABASE so pg_restore knows the target database." >&2
	exit 1
fi

# ── Resolve which backup to restore ────────────────────────────────────────
ARG="${1:-}"
if [[ -z "$ARG" ]]; then
	# Latest = last of the chronologically-sorted dumps. Filter to our own
	# podcastfy-<stamp>.dump pattern so a stray object under the prefix can't be
	# selected as the "backup" to restore.
	NAME="$(aws s3 ls "s3://${DB_BACKUP_S3_BUCKET}/${DB_BACKUP_S3_PREFIX}" | awk '{print $4}' | grep -E '^podcastfy-[0-9]{8}T[0-9]{6}Z\.dump$' | sort | tail -n1)"
	if [[ -z "$NAME" ]]; then
		echo "No backups found under s3://${DB_BACKUP_S3_BUCKET}/${DB_BACKUP_S3_PREFIX}" >&2
		exit 1
	fi
	KEY="${DB_BACKUP_S3_PREFIX}${NAME}"
else
	# Accept either a bare filename or a full prefixed key.
	if [[ "$ARG" == "${DB_BACKUP_S3_PREFIX}"* ]]; then
		KEY="$ARG"
	else
		KEY="${DB_BACKUP_S3_PREFIX}${ARG}"
	fi
fi

SRC="s3://${DB_BACKUP_S3_BUCKET}/${KEY}"
echo "Selected backup: ${SRC}"

# ── Guard: restoring clobbers the live database ────────────────────────────
if [[ "${DB_RESTORE_FORCE:-}" != "1" ]]; then
	echo
	echo "WARNING: pg_restore --clean will DROP and recreate objects in the target database."
	read -r -p "Type 'yes' to proceed: " CONFIRM
	if [[ "$CONFIRM" != "yes" ]]; then
		echo "Aborted."
		exit 1
	fi
fi

DUMP_FILE="$(mktemp -t podcastfy-restore-XXXXXX.dump)"
trap 'rm -f "$DUMP_FILE"' EXIT

echo "Downloading ${SRC}..."
aws s3 cp "$SRC" "$DUMP_FILE"

echo "Restoring into target database..."
# --single-transaction + --exit-on-error make the restore atomic: any failure
# rolls the whole thing back, so a half-applied --clean can't leave the live DB
# corrupted. --clean --if-exists makes it idempotent over an existing schema.
pg_restore --single-transaction --exit-on-error --clean --if-exists --no-owner \
	--dbname "$TARGET_DB" "$DUMP_FILE"

echo "Restore complete from ${SRC}."
