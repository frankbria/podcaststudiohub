#!/usr/bin/env bash
# select-review-pr.sh — Selects a maintainer PR needing review fixes.
# Usage: select-review-pr.sh [force_pr_number]
# Outputs to $GITHUB_OUTPUT: pr_number, tier, round, linked_issue
# Exits 0 with pr_number="" if no eligible PRs found.
set -euo pipefail

FORCE_PR="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"

# ── Helpers ───────────────────────────────────────────

# Determine governance tier for a PR via its linked issue
get_tier_for_pr() {
	local pr_num="$1"
	local issue_num
	issue_num=$(gh pr view "$pr_num" --json body \
		--jq '.body' 2>/dev/null \
		| grep -oP '(?:Closes|Fixes|Resolves)\s+#\K\d+' \
		| head -1 || echo "")
	if [[ -n "$issue_num" ]]; then
		"$SCRIPT_DIR/determine-governance-tier.sh" "$issue_num"
	else
		echo "T1" # Default to notify if no linked issue
	fi
}

# Count review rounds from labels (returns next round number)
get_round() {
	local pr_num="$1"
	local labels
	labels=$(gh pr view "$pr_num" --json labels --jq '[.labels[].name] | join(",")' 2>/dev/null || echo "")
	if echo "$labels" | grep -q "review-round-3"; then echo 4; return; fi
	if echo "$labels" | grep -q "review-round-2"; then echo 3; return; fi
	if echo "$labels" | grep -q "review-round-1"; then echo 2; return; fi
	echo 1
}

# Extract linked issue number from PR body
get_linked_issue() {
	local pr_num="$1"
	gh pr view "$pr_num" --json body \
		--jq '.body' 2>/dev/null \
		| grep -oP '(?:Closes|Fixes|Resolves)\s+#\K\d+' \
		| head -1 || echo ""
}

# Write outputs (works both in CI with GITHUB_OUTPUT and locally to stdout)
output() {
	local key="$1" val="$2"
	if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
		echo "$key=$val" >> "$GITHUB_OUTPUT"
	fi
	echo "$key=$val" >&2
}

# ── Force mode ────────────────────────────────────────

if [[ -n "$FORCE_PR" ]]; then
	TIER=$(get_tier_for_pr "$FORCE_PR")
	ROUND=$(get_round "$FORCE_PR")
	LINKED=$(get_linked_issue "$FORCE_PR")
	output "pr_number" "$FORCE_PR"
	output "tier" "$TIER"
	output "round" "$ROUND"
	output "linked_issue" "$LINKED"
	echo "::notice::Force-selected PR #$FORCE_PR ($TIER, round $ROUND)"
	exit 0
fi

# ── Auto-select ──────────────────────────────────────

# Find open maintainer PRs with review-changes-requested label
PRS=$(gh pr list --state open \
	--label "review-changes-requested" \
	--json number,headRefName,labels,createdAt \
	--limit 20 2>/dev/null || echo "[]")

# Filter to maintainer/ branches only
PRS=$(echo "$PRS" | jq '[.[] | select(.headRefName | startswith("maintainer/"))]')

# Exclude security-concern and maintainer-needs-human
PRS=$(echo "$PRS" | jq '[.[] | select(
	([.labels[].name] | any(. == "security-concern" or . == "maintainer-needs-human")) | not
)]')

# Exclude PRs that have already hit max rounds (review-round-3)
PRS=$(echo "$PRS" | jq '[.[] | select(
	([.labels[].name] | any(. == "review-round-3")) | not
)]')

# Sort by creation date (oldest first — FIFO)
PRS=$(echo "$PRS" | jq 'sort_by(.createdAt)')

SELECTED=$(echo "$PRS" | jq -r '.[0].number // empty')

if [[ -z "$SELECTED" || "$SELECTED" == "null" ]]; then
	# Also check for PRs with review-approved that are T0 and can be auto-merged
	APPROVED_PRS=$(gh pr list --state open \
		--label "review-approved" \
		--json number,headRefName,labels,createdAt \
		--limit 20 2>/dev/null || echo "[]")

	APPROVED_PRS=$(echo "$APPROVED_PRS" | jq '[.[] | select(.headRefName | startswith("maintainer/"))]')
	APPROVED_PRS=$(echo "$APPROVED_PRS" | jq '[.[] | select(
		([.labels[].name] | any(. == "security-concern" or . == "maintainer-needs-human" or . == "ready-to-merge")) | not
	)]')
	APPROVED_PRS=$(echo "$APPROVED_PRS" | jq 'sort_by(.createdAt)')
	SELECTED=$(echo "$APPROVED_PRS" | jq -r '.[0].number // empty')

	if [[ -z "$SELECTED" || "$SELECTED" == "null" ]]; then
		echo "::notice::No maintainer PRs need review processing"
		output "pr_number" ""
		exit 0
	fi
fi

TIER=$(get_tier_for_pr "$SELECTED")
ROUND=$(get_round "$SELECTED")
LINKED=$(get_linked_issue "$SELECTED")

output "pr_number" "$SELECTED"
output "tier" "$TIER"
output "round" "$ROUND"
output "linked_issue" "$LINKED"
echo "::notice::Selected PR #$SELECTED ($TIER, round $ROUND)"
