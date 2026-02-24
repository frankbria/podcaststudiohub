#!/usr/bin/env bash
# check-circuit-breakers.sh — Reads config.yml and state.json, outputs whether the loop should run.
# Exit code 0 = proceed, exit code 1 = skip run.
# Outputs JSON with { "should_run": bool, "reason": string } to stdout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"
STATE="$REPO_ROOT/.github/repo-maintainer/state.json"

if ! command -v yq &>/dev/null; then
	echo '{"should_run":false,"reason":"yq not installed"}' && exit 1
fi
if ! command -v jq &>/dev/null; then
	echo '{"should_run":false,"reason":"jq not installed"}' && exit 1
fi

# Read operating mode
MODE=$(yq -r '.operating_mode // "maintain"' "$CONFIG")

# Read state
PAUSED=$(jq -r '.loop.paused // false' "$STATE")
LAST_RUN=$(jq -r '.loop.last_run_at // empty' "$STATE")
PRS_TODAY=$(jq -r '.counters.prs_today // 0' "$STATE")
COST_TODAY=$(jq -r '.counters.estimated_cost_today_usd // 0' "$STATE")
COST_MONTH=$(jq -r '.counters.estimated_cost_this_month_usd // 0' "$STATE")
DAY_RESET=$(jq -r '.counters.day_reset_date // empty' "$STATE")
MONTH_RESET=$(jq -r '.counters.month_reset_date // empty' "$STATE")
REJECTED=$(jq -r '.feedback.consecutive_rejected_prs // 0' "$STATE")
CI_FAILURES=$(jq -r '.feedback.consecutive_ci_failures // 0' "$STATE")

# Read mode-specific limits
MAX_PRS=$(yq -r ".limits.${MODE}.max_prs_per_day // 2" "$CONFIG")
MAX_COST_DAY=$(yq -r ".limits.${MODE}.budget_usd_per_day // 30" "$CONFIG")
MAX_COST_MONTH=$(yq -r ".limits.${MODE}.budget_usd_per_month // 300" "$CONFIG")
COOLDOWN=$(yq -r ".schedule.${MODE}.cooldown_minutes // 30" "$CONFIG")

TODAY=$(date -u +%Y-%m-%d)
THIS_MONTH=$(date -u +%Y-%m)
NOW_EPOCH=$(date -u +%s)

# Reset daily counters if new day
if [[ "$DAY_RESET" != "$TODAY" ]]; then
	PRS_TODAY=0
	COST_TODAY=0
fi

# Reset monthly counters if new month
if [[ "${MONTH_RESET:-}" != "$THIS_MONTH" ]]; then
	COST_MONTH=0
fi

# --- Circuit breaker checks ---

skip() {
	echo "{\"should_run\":false,\"reason\":\"$1\"}"
	exit 1
}

# 1. Paused?
if [[ "$PAUSED" == "true" ]]; then
	skip "Loop is paused"
fi

# 2. Consecutive PR rejections
if [[ "$REJECTED" -ge 2 ]]; then
	skip "2+ consecutive PR rejections — auto-paused"
fi

# 3. Consecutive CI failures
if [[ "$CI_FAILURES" -ge 3 ]]; then
	skip "3+ consecutive CI failures — auto-paused"
fi

# 4. Daily PR limit
if [[ "$PRS_TODAY" -ge "$MAX_PRS" ]]; then
	skip "Daily PR limit reached ($PRS_TODAY/$MAX_PRS)"
fi

# 5. Daily budget
if awk "BEGIN {exit !($COST_TODAY >= $MAX_COST_DAY)}"; then
	skip "Daily budget exceeded (\$$COST_TODAY/\$$MAX_COST_DAY)"
fi

# 6. Monthly budget
if awk "BEGIN {exit !($COST_MONTH >= $MAX_COST_MONTH)}"; then
	skip "Monthly budget exceeded (\$$COST_MONTH/\$$MAX_COST_MONTH)"
fi

# 7. Cooldown period
if [[ -n "$LAST_RUN" ]]; then
	LAST_EPOCH=$(date -u -d "$LAST_RUN" +%s 2>/dev/null || echo 0)
	ELAPSED_MIN=$(( (NOW_EPOCH - LAST_EPOCH) / 60 ))
	if [[ "$ELAPSED_MIN" -lt "$COOLDOWN" ]]; then
		skip "Cooldown active (${ELAPSED_MIN}m/${COOLDOWN}m)"
	fi
fi

# All checks passed
echo "{\"should_run\":true,\"reason\":\"all checks passed\",\"mode\":\"$MODE\",\"prs_today\":$PRS_TODAY,\"budget_remaining_today\":$(awk "BEGIN {print $MAX_COST_DAY - $COST_TODAY}")}"
exit 0
