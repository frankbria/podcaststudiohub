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

# CONFIG SET alone is lost on restart — persist it into redis.conf. Fails on
# a config-file-less redis (e.g. ad-hoc `redis-server` with no conf); that is
# deliberate: such an instance can't hold the setting across restarts anyway.
$REDIS_CLI CONFIG REWRITE >/dev/null

# Trust but verify: read the setting back rather than assuming it stuck.
STATE="$($REDIS_CLI CONFIG GET appendonly | tail -1)"
if [[ "$STATE" != "yes" ]]; then
	echo "appendonly readback returned '$STATE', expected 'yes'" >&2
	exit 1
fi

echo "Redis AOF persistence enabled (appendonly=yes, appendfsync=everysec) and persisted to redis.conf."
