#!/usr/bin/env bash
# select-next-issue.sh — Selects the next issue to implement based on phase + priority.
# Outputs JSON: { "issue_number": N, "title": "...", "tier": "T0"|"T1"|"T2"|"T3" }
# Exit code 1 if no eligible issues found.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"
STATE="$REPO_ROOT/.github/repo-maintainer/state.json"

# Allow overriding with a specific issue number
FORCE_ISSUE="${1:-}"

if [[ -n "$FORCE_ISSUE" ]]; then
	ISSUE_JSON=$(gh issue view "$FORCE_ISSUE" --json number,title,labels)
	ISSUE_NUMBER=$(echo "$ISSUE_JSON" | jq -r '.number')
	ISSUE_TITLE=$(echo "$ISSUE_JSON" | jq -r '.title')
	ISSUE_LABELS=$(echo "$ISSUE_JSON" | jq -r '[.labels[].name] | join(",")')
	TIER=$("$SCRIPT_DIR/determine-governance-tier.sh" "$ISSUE_NUMBER")
	jq -n --argjson num "$ISSUE_NUMBER" --arg title "$ISSUE_TITLE" --arg tier "$TIER" --arg labels "$ISSUE_LABELS" \
		'{issue_number: $num, title: $title, tier: $tier, labels: $labels}'
	exit 0
fi

# Read current phase from state
CURRENT_PHASE=$(jq -r '.phases.current_phase // "phase-1"' "$STATE")

# Fetch issues with plan-ready label in current phase, sorted by priority
# Priority order: p0 > p1 > p2 > p3
ISSUES=$(gh issue list \
	--state open \
	--label "plan-ready" \
	--label "$CURRENT_PHASE" \
	--json number,title,labels \
	--limit 50 2>/dev/null || echo "[]")

if [[ "$ISSUES" == "[]" || -z "$ISSUES" ]]; then
	# Try without phase label (fallback for unlabeled issues)
	ISSUES=$(gh issue list \
		--state open \
		--label "plan-ready" \
		--json number,title,labels \
		--limit 50 2>/dev/null || echo "[]")
fi

if [[ "$ISSUES" == "[]" || -z "$ISSUES" ]]; then
	echo '{"issue_number":null,"reason":"No eligible issues found with plan-ready label"}'
	exit 1
fi

# Filter out skip/human-only issues and issues with open maintainer PRs
FILTERED=$(echo "$ISSUES" | jq '[
	.[] | select(
		([.labels[].name] | any(. == "maintainer-skip" or . == "maintainer-human-only")) | not
	)
]')

# Sort by priority (p0 first, then p1, p2, p3, then no priority)
SORTED=$(echo "$FILTERED" | jq 'sort_by(
	if [.labels[].name] | any(startswith("priority-p0")) then 0
	elif [.labels[].name] | any(startswith("priority-p1")) then 1
	elif [.labels[].name] | any(startswith("priority-p2")) then 2
	elif [.labels[].name] | any(startswith("priority-p3")) then 3
	else 4 end
)')

# Read max_implementation_attempts from config (default 2)
MAX_ATTEMPTS=$(yq -r '.limits.max_implementation_attempts // 2' "$CONFIG")

# Build a list of issues that have hit max consecutive failures in history.
# Groups failure entries by issue number and skips those with >= max attempts.
FAILED_ISSUES=$(jq -r --argjson max "$MAX_ATTEMPTS" '
	[.history[] | select(.result == "failure")]
	| group_by(.issue)
	| map(select(length >= $max))
	| map(.[0].issue)
	| .[]
' "$STATE" 2>/dev/null || echo "")

# Extract just the issue numbers in priority order, then check each for open PRs
ISSUE_NUMBERS=$(echo "$SORTED" | jq -r '.[].number')

SELECTED_NUMBER=""
SKIP_REASON=""
TRIED_NUMBERS=""
SOURCE_JSON="$SORTED"

for NUM in $ISSUE_NUMBERS; do
	TRIED_NUMBERS="$TRIED_NUMBERS $NUM"
	# Skip issues that have exceeded max implementation attempts
	if echo "$FAILED_ISSUES" | grep -qw "$NUM"; then
		echo "Skipping issue #${NUM}: hit ${MAX_ATTEMPTS} consecutive failures" >&2
		gh issue edit "$NUM" --add-label "maintainer-skip" 2>/dev/null || true
		SKIP_REASON="exhausted"
		continue
	fi

	# Check if there's already an open PR for this issue
	EXISTING_PR=$(gh pr list --state open --json number,headRefName \
		--jq "[.[] | select(.headRefName | startswith(\"maintainer/issue-${NUM}\"))]" \
		2>/dev/null || echo "[]")
	if [[ "$EXISTING_PR" != "[]" && -n "$EXISTING_PR" ]]; then
		SKIP_REASON="open_pr"
		continue
	fi

	SELECTED_NUMBER="$NUM"
	break
done

# Cross-phase fallback: if all current-phase candidates were exhausted/skipped,
# try ALL plan-ready issues across all phases
if [[ -z "$SELECTED_NUMBER" ]]; then
	echo "Phase $CURRENT_PHASE exhausted, trying cross-phase fallback..." >&2
	ALL_ISSUES=$(gh issue list \
		--state open \
		--label "plan-ready" \
		--json number,title,labels \
		--limit 50 2>/dev/null || echo "[]")

	# Filter skip/human-only, exclude already-tried numbers, sort by priority
	ALL_FILTERED=$(echo "$ALL_ISSUES" | jq '[
		.[] | select(
			([.labels[].name] | any(. == "maintainer-skip" or . == "maintainer-human-only")) | not
		)
	]')
	ALL_SORTED=$(echo "$ALL_FILTERED" | jq 'sort_by(
		if [.labels[].name] | any(startswith("priority-p0")) then 0
		elif [.labels[].name] | any(startswith("priority-p1")) then 1
		elif [.labels[].name] | any(startswith("priority-p2")) then 2
		elif [.labels[].name] | any(startswith("priority-p3")) then 3
		else 4 end
	)')
	ALL_NUMBERS=$(echo "$ALL_SORTED" | jq -r '.[].number')

	for NUM in $ALL_NUMBERS; do
		# Skip issues already checked in pass 1
		if echo "$TRIED_NUMBERS" | grep -qw "$NUM"; then
			continue
		fi
		# Skip issues that have exceeded max implementation attempts
		if echo "$FAILED_ISSUES" | grep -qw "$NUM"; then
			echo "Skipping issue #${NUM} (cross-phase): hit ${MAX_ATTEMPTS} failures" >&2
			gh issue edit "$NUM" --add-label "maintainer-skip" 2>/dev/null || true
			SKIP_REASON="exhausted"
			continue
		fi
		# Check for open PR
		EXISTING_PR=$(gh pr list --state open --json number,headRefName \
			--jq "[.[] | select(.headRefName | startswith(\"maintainer/issue-${NUM}\"))]" \
			2>/dev/null || echo "[]")
		if [[ "$EXISTING_PR" != "[]" && -n "$EXISTING_PR" ]]; then
			SKIP_REASON="open_pr"
			continue
		fi

		SELECTED_NUMBER="$NUM"
		SOURCE_JSON="$ALL_SORTED"
		break
	done
fi

if [[ -z "$SELECTED_NUMBER" ]]; then
	case "$SKIP_REASON" in
		exhausted) REASON="All plan-ready issues have exhausted max implementation attempts ($MAX_ATTEMPTS)" ;;
		open_pr)   REASON="All eligible issues already have open PRs" ;;
		*)         REASON="No eligible plan-ready issues found" ;;
	esac
	echo "{\"issue_number\":null,\"reason\":\"$REASON\"}"
	exit 1
fi

ISSUE_NUMBER="$SELECTED_NUMBER"
ISSUE_TITLE=$(echo "$SOURCE_JSON" | jq -r ".[] | select(.number == $SELECTED_NUMBER) | .title" | tr -d '\n')
ISSUE_LABELS=$(echo "$SOURCE_JSON" | jq -r ".[] | select(.number == $SELECTED_NUMBER) | [.labels[].name] | join(\",\")")

# Determine governance tier
TIER=$("$SCRIPT_DIR/determine-governance-tier.sh" "$ISSUE_NUMBER")

# Output clean JSON
jq -n --argjson num "$ISSUE_NUMBER" --arg title "$ISSUE_TITLE" --arg tier "$TIER" --arg labels "$ISSUE_LABELS" \
	'{issue_number: $num, title: $title, tier: $tier, labels: $labels}'
