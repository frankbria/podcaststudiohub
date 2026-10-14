#!/usr/bin/env bash
# CRAP gate over coverage from only the tests you name (the full gate runs every suite, ~12 min).
# Usage: scripts/crap-targeted.sh [--api "<pytest paths>"] [--web "<jest pattern>"]
# Limit: functions your selection does not exercise show as uncovered. Pick the tests that cover the change.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"; out="$(mktemp -d)"; api=""; web=""
while [ $# -gt 0 ]; do case "$1" in --api) api="$2"; shift 2;; --web) web="$2"; shift 2;; *) echo "unknown arg $1"; exit 2;; esac; done
: > "$out/lcov.info"
if [ -n "$api" ]; then
  # Local test DB/Redis as in .github/workflows/test.yml (dummy, non-secret values); override via env.
  export JWT_SECRET_KEY="${JWT_SECRET_KEY:-test-secret-key-at-least-32-characters-long}"
  export ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')}"
  export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://podcastfy:podcastfy_password@localhost:5433/podcastfy}"
  export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://podcastfy_app:podcastfy_app_password@localhost:5433/podcastfy}"
  export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}" CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://localhost:6379/0}" CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://localhost:6379/0}"
  # shellcheck disable=SC2086  # $api is a deliberate list of test paths
  (cd "$root/apps/api" && uv run pytest $api -q -p no:cacheprovider --cov=src --cov-report="lcov:$out/api.info" --cov-fail-under=0)
  sed 's|^SF:src/|SF:apps/api/src/|' "$out/api.info" >> "$out/lcov.info"
fi
if [ -n "$web" ]; then
  # The repo's global 80% threshold cannot hold for a subset of suites.
  (cd "$root/apps/web" && npx jest "$web" --coverage --coverageReporters=lcov --coverageDirectory="$out/web" --coverageThreshold='{}')
  sed 's|^SF:src/|SF:apps/web/src/|' "$out/web/lcov.info" >> "$out/lcov.info"
fi
# --coverage-command, not --lcov: given --lcov, the gate still runs its own (full) coverage command.
node "$(ls -d ~/.claude/plugins/cache/eigenwise-toolshed/quartermaster/*/ | sort -V | tail -1)bin/quartermaster.js" crap \
  --project "$root" --coverage-command "cp '$out/lcov.info' \"\$QUARTERMASTER_COVERAGE_DIR/lcov.info\""
