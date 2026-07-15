#!/usr/bin/env bash
#
# Enable Redis AOF persistence on the VPS (issue #319).
#
# Redis is the Celery broker + result backend + OAuth-state store. Without
# persistence, a restart silently drops every queued/in-flight generation job.
# AOF with appendfsync=everysec bounds that loss to <=1s of writes; the
# reap_stuck_episodes beat task remains the backstop for anything stranded
# (see deployment/README.md "Redis durability").
#
# Idempotent — safe to re-run. Run on the VPS as any user that can reach
# redis (default localhost, no auth):
#
#   bash deployment/scripts/configure-redis-persistence.sh
#
# Configuration (env):
#   REDIS_CLI   redis-cli invocation, e.g. "redis-cli -p 6380" (default: redis-cli)

set -euo pipefail

REDIS_CLI="${REDIS_CLI:-redis-cli}"

$REDIS_CLI CONFIG SET appendonly yes >/dev/null
$REDIS_CLI CONFIG SET appendfsync everysec >/dev/null

# CONFIG SET alone is lost on restart — persist it into redis.conf. redis-cli
# exits 0 even when the server replies with an ERR, so `set -e` can't catch a
# refused rewrite (unwritable/absent redis.conf); capture the reply and check
# it. Hard-fail: an instance that can't persist the setting silently loses AOF
# on its next restart, which is exactly the failure this script exists to stop.
REWRITE="$($REDIS_CLI CONFIG REWRITE 2>&1 || true)"
if [[ "$REWRITE" != "OK" ]]; then
	echo "CONFIG REWRITE failed: ${REWRITE}" >&2
	echo "AOF is live now but would be lost on restart — fix redis.conf permissions and re-run." >&2
	exit 1
fi

# Trust but verify: read the setting back rather than assuming it stuck.
STATE="$($REDIS_CLI CONFIG GET appendonly | tail -1)"
if [[ "$STATE" != "yes" ]]; then
	echo "appendonly readback returned '$STATE', expected 'yes'" >&2
	exit 1
fi

echo "Redis AOF persistence enabled (appendonly=yes, appendfsync=everysec) and persisted to redis.conf."
