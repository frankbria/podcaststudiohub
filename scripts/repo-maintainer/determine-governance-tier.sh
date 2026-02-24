#!/usr/bin/env bash
# determine-governance-tier.sh — Classifies an issue into T0/T1/T2/T3.
# Usage: determine-governance-tier.sh <issue_number>
# Outputs: T0, T1, T2, or T3
set -euo pipefail

ISSUE_NUMBER="${1:?Usage: determine-governance-tier.sh <issue_number>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"
STATE="$REPO_ROOT/.github/repo-maintainer/state.json"

MODE=$(yq -r '.operating_mode // "maintain"' "$CONFIG")

# Get issue labels
LABELS=$(gh issue view "$ISSUE_NUMBER" --json labels --jq '[.labels[].name] | join("\n")' 2>/dev/null || echo "")

# Start at T0, escalate based on rules
TIER=0

# Check human_only labels → T3
HUMAN_LABELS=$(yq -r '.governance.human_only.labels[]' "$CONFIG" 2>/dev/null || true)
for LABEL in $HUMAN_LABELS; do
	if echo "$LABELS" | grep -qxF "$LABEL"; then
		echo "T3"
		exit 0
	fi
done

# Check approve labels → T2
APPROVE_LABELS=$(yq -r '.governance.approve.labels[]' "$CONFIG" 2>/dev/null || true)
for LABEL in $APPROVE_LABELS; do
	if echo "$LABELS" | grep -qxF "$LABEL"; then
		TIER=2
	fi
done

# Check notify labels → T1 (only if not already T2+)
if [[ "$TIER" -lt 1 ]]; then
	NOTIFY_LABELS=$(yq -r '.governance.notify.labels[]' "$CONFIG" 2>/dev/null || true)
	for LABEL in $NOTIFY_LABELS; do
		if echo "$LABELS" | grep -qxF "$LABEL"; then
			TIER=1
		fi
	done
fi

# Check proving period — override to T1+ if not graduated
GRADUATED=$(jq -r '.proving.graduated // false' "$STATE")
if [[ "$GRADUATED" != "true" && "$TIER" -lt 1 ]]; then
	TIER=1
fi

echo "T${TIER}"
