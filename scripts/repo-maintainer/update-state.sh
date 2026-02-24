#!/usr/bin/env bash
# update-state.sh — Atomically updates state.json after a loop run.
# Usage: update-state.sh <action> [args...]
# Actions:
#   record-run <issue_number> <pr_number> <result:success|failure> <cost_usd>
#   pause <reason>
#   resume
#   reset-day
#   advance-phase
#   switch-mode <build|maintain>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"
STATE="$REPO_ROOT/.github/repo-maintainer/state.json"

ACTION="${1:?Usage: update-state.sh <action> [args...]}"
shift

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)
THIS_MONTH=$(date -u +%Y-%m)

# Helper: reset counters if needed
reset_if_needed() {
	local day_reset
	day_reset=$(jq -r '.counters.day_reset_date // ""' "$STATE")
	if [[ "$day_reset" != "$TODAY" ]]; then
		jq ".counters.prs_today = 0 | .counters.issues_created_today = 0 | .counters.estimated_cost_today_usd = 0 | .counters.day_reset_date = \"$TODAY\"" "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
	fi
	local month_reset
	month_reset=$(jq -r '.counters.month_reset_date // ""' "$STATE")
	if [[ "$month_reset" != "$THIS_MONTH" ]]; then
		jq ".counters.prs_this_month = 0 | .counters.estimated_cost_this_month_usd = 0 | .counters.month_reset_date = \"$THIS_MONTH\"" "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
	fi
}

case "$ACTION" in
	record-run)
		ISSUE="${1:?Missing issue_number}"
		PR="${2:?Missing pr_number}"
		RESULT="${3:?Missing result (success|failure)}"
		COST="${4:-0}"

		reset_if_needed

		REQUIRED=$(yq -r '.proving.required_successes // 5' "$CONFIG")

		if [[ "$RESULT" == "success" ]]; then
			# Increment counters and proving
			jq --argjson issue "$ISSUE" \
				--argjson pr "$PR" \
				--arg cost "$COST" \
				--arg now "$NOW" \
				--argjson required "$REQUIRED" \
				'
				.loop.last_run_at = $now |
				.loop.last_run_result = "success" |
				.loop.last_implemented_issue = $issue |
				.loop.active_pr = $pr |
				.counters.prs_today += 1 |
				.counters.prs_this_month += 1 |
				.counters.estimated_cost_today_usd += ($cost | tonumber) |
				.counters.estimated_cost_this_month_usd += ($cost | tonumber) |
				.feedback.consecutive_rejected_prs = 0 |
				.feedback.consecutive_ci_failures = 0 |
				.proving.consecutive_successes += 1 |
				(if .proving.consecutive_successes >= $required then .proving.graduated = true else . end) |
				.history += [{"issue": $issue, "pr": $pr, "result": "success", "cost_usd": ($cost | tonumber), "at": $now}]
				' "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
		else
			# Record failure, reset proving
			jq --argjson issue "$ISSUE" \
				--arg now "$NOW" \
				--arg cost "$COST" \
				'
				.loop.last_run_at = $now |
				.loop.last_run_result = "failure" |
				.loop.last_implemented_issue = $issue |
				.counters.estimated_cost_today_usd += ($cost | tonumber) |
				.counters.estimated_cost_this_month_usd += ($cost | tonumber) |
				.feedback.consecutive_ci_failures += 1 |
				.proving.consecutive_successes = 0 |
				.proving.graduated = false |
				.history += [{"issue": $issue, "pr": null, "result": "failure", "cost_usd": ($cost | tonumber), "at": $now}]
				' "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
		fi
		;;

	record-rejection)
		jq '.feedback.consecutive_rejected_prs += 1 | .proving.consecutive_successes = 0 | .proving.graduated = false' "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
		;;

	pause)
		REASON="${1:-Manual pause}"
		jq --arg reason "$REASON" '.loop.paused = true | .loop.pause_reason = $reason' "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
		;;

	resume)
		jq '.loop.paused = false | .loop.pause_reason = null' "$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
		;;

	advance-phase)
		PHASES=$(yq -r '.issue_selection.phases[]' "$CONFIG")
		CURRENT=$(jq -r '.phases.current_phase' "$STATE")
		NEXT=""
		FOUND_CURRENT=false
		for P in $PHASES; do
			if [[ "$FOUND_CURRENT" == "true" ]]; then
				NEXT="$P"
				break
			fi
			if [[ "$P" == "$CURRENT" ]]; then
				FOUND_CURRENT=true
			fi
		done
		if [[ -n "$NEXT" ]]; then
			jq --arg current "$CURRENT" --arg next "$NEXT" \
				'.phases.completed_phases += [$current] | .phases.current_phase = $next' \
				"$STATE" > "${STATE}.tmp" && mv "${STATE}.tmp" "$STATE"
			echo "Advanced from $CURRENT to $NEXT"
		else
			echo "Already at last phase ($CURRENT)"
		fi
		;;

	switch-mode)
		NEW_MODE="${1:?Missing mode (build|maintain)}"
		yq -i ".operating_mode = \"$NEW_MODE\"" "$CONFIG"
		echo "Switched to $NEW_MODE mode"
		;;

	*)
		echo "Unknown action: $ACTION" >&2
		echo "Usage: update-state.sh <record-run|record-rejection|pause|resume|advance-phase|switch-mode>" >&2
		exit 1
		;;
esac
