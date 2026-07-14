#!/usr/bin/env bash
#
# Nightly off-host PostgreSQL backup for the Podcastfy Studio VPS (issue #293).
#
# All durable tenant state (users, auth, projects, episodes, RSS feeds,
# distribution targets with encrypted OAuth tokens, Stripe billing) lives only
# in the single VPS Postgres datadir. This takes a logical custom-format dump,
# compresses it, ships it to S3 object storage, and prunes backups older than
# the retention window. Run nightly via install-db-backup-timer.sh.
#
# Idempotent and safe to run by hand for an on-demand backup:
#   bash deployment/scripts/backup-db.sh
#
# Configuration (env, with sensible defaults):
#   DATABASE_URL              postgres conn string (or use the PG* vars below)
#   PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD   standard libpq vars (fallback)
#   DB_BACKUP_S3_BUCKET       bucket for dumps (default: $AWS_S3_BUCKET)
#   DB_BACKUP_S3_PREFIX       key prefix      (default: db-backups/)
#   DB_BACKUP_RETENTION_DAYS  prune objects older than N days (default: 14)
#   AWS_REGION                passed through to the aws CLI

set -euo pipefail

DB_BACKUP_S3_BUCKET="${DB_BACKUP_S3_BUCKET:-${AWS_S3_BUCKET:-}}"
DB_BACKUP_S3_PREFIX="${DB_BACKUP_S3_PREFIX:-db-backups/}"
DB_BACKUP_RETENTION_DAYS="${DB_BACKUP_RETENTION_DAYS:-14}"

if [[ -z "$DB_BACKUP_S3_BUCKET" ]]; then
	echo "DB_BACKUP_S3_BUCKET (or AWS_S3_BUCKET) must be set — refusing a host-only backup." >&2
	exit 1
fi

# Prefer the privileged migration role (issue #319): tenant tables carry
# FORCE ROW LEVEL SECURITY (migration 014), and pg_dump as the RLS-subject
# podcastfy_app role either errors out or — with row security enabled —
# silently omits every tenant row, producing a non-empty but unusable dump.
# MIGRATION_DATABASE_URL is the BYPASSRLS owner the app .env already defines
# for Alembic (issue #301); fall back to DATABASE_URL for single-role setups.
#
# The conn string is passed explicitly so a +asyncpg driver suffix
# (SQLAlchemy style) is normalised to a plain postgres:// URL pg_dump
# understands; without one, pg_dump falls back to the libpq PG* variables.
SRC_URL="${MIGRATION_DATABASE_URL:-${DATABASE_URL:-}}"
CONN=()
if [[ -n "$SRC_URL" ]]; then
	CONN=("${SRC_URL/postgresql+asyncpg:/postgresql:}")
	CONN=("${CONN[0]/postgres+asyncpg:/postgres:}")
fi

# ponytail: timestamp from `date`, not a fixed clock — backups must be unique &
# sortable. UTC so retention math is DST-proof.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_FILE="$(mktemp -t podcastfy-db-XXXXXX.dump)"
trap 'rm -f "$DUMP_FILE"' EXIT

KEY="${DB_BACKUP_S3_PREFIX}podcastfy-${STAMP}.dump"
DEST="s3://${DB_BACKUP_S3_BUCKET}/${KEY}"

echo "Dumping database -> ${DEST}"
# -Fc = custom format: already zlib-compressed and gives selective, parallel
# pg_restore. No extra gzip layer — it would double-compress for ~0 gain.
pg_dump -Fc "${CONN[@]}" >"$DUMP_FILE"

if [[ ! -s "$DUMP_FILE" ]]; then
	echo "pg_dump produced an empty file — aborting before upload." >&2
	exit 1
fi

aws s3 cp "$DUMP_FILE" "$DEST"
echo "Uploaded $(du -h "$DUMP_FILE" | cut -f1) to ${DEST}"

# ── Retention: prune objects older than the window ─────────────────────────
# `aws s3 ls` reports each object's last-modified date; delete anything past the
# cutoff. ponytail: O(n) scan over one prefix — fine for nightly dumps; switch
# to an S3 lifecycle rule if the prefix ever holds thousands of objects.
CUTOFF="$(date -u -d "${DB_BACKUP_RETENTION_DAYS} days ago" +%Y-%m-%d)"
echo "Pruning backups older than ${CUTOFF} (retention ${DB_BACKUP_RETENTION_DAYS}d)"

aws s3 ls "s3://${DB_BACKUP_S3_BUCKET}/${DB_BACKUP_S3_PREFIX}" | while read -r line; do
	# `aws s3 ls <prefix>/` lines: "2026-06-01 03:00:00  123456 podcastfy-….dump.gz"
	# (the name is relative to the listed prefix, so we re-add the prefix to delete).
	file_date="$(echo "$line" | awk '{print $1}')"
	file_name="$(echo "$line" | awk '{print $4}')"
	[[ -z "$file_name" ]] && continue
	# Only ever prune objects this script created — never unrelated keys that
	# happen to share the prefix. Match our own podcastfy-<stamp>.dump pattern.
	[[ "$file_name" == podcastfy-*.dump ]] || continue
	if [[ "$file_date" < "$CUTOFF" ]]; then
		echo "  deleting aged-out backup: ${file_name}"
		aws s3 rm "s3://${DB_BACKUP_S3_BUCKET}/${DB_BACKUP_S3_PREFIX}${file_name}"
	fi
done

echo "Backup complete."
