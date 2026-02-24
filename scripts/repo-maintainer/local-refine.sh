#!/usr/bin/env bash
# local-refine.sh — Mode B: Post-implementation plan refinement via Claude Code.
# Runs after an issue is implemented to review and adjust remaining issues.
#
# Usage: ./local-refine.sh [last_implemented_issue_number]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
STATE="$REPO_ROOT/.github/repo-maintainer/state.json"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"

LAST_ISSUE="${1:-$(jq -r '.loop.last_implemented_issue // empty' "$STATE")}"

if [[ -z "$LAST_ISSUE" ]]; then
	echo "No last implemented issue found. Skipping refinement."
	exit 0
fi

CURRENT_PHASE=$(jq -r '.phases.current_phase // "phase-1"' "$STATE")

echo "=== Plan Refinement ==="
echo "Last implemented: #$LAST_ISSUE"
echo "Current phase: $CURRENT_PHASE"

# Check if all issues in current phase are done
OPEN_IN_PHASE=$(gh issue list --state open --label "$CURRENT_PHASE" --json number --jq 'length' 2>/dev/null || echo "999")
echo "Open issues in $CURRENT_PHASE: $OPEN_IN_PHASE"

if [[ "$OPEN_IN_PHASE" -eq 0 ]]; then
	echo "All issues in $CURRENT_PHASE are complete. Advancing phase."
	"$SCRIPT_DIR/update-state.sh" advance-phase
fi

# Run Claude Code for plan refinement
claude -p "You just implemented issue #${LAST_ISSUE}. Review the remaining open issues and suggest adjustments.

Current phase: $CURRENT_PHASE
Open issues in phase: $OPEN_IN_PHASE

Tasks:
1. Run: gh issue list --state open --label '$CURRENT_PHASE' --json number,title,labels
2. Check if any remaining issues have prerequisites that are now met
3. Check if any issues should be modified based on what was learned during implementation
4. Create max 3 new issues if gaps were discovered
5. Close any issues that are now redundant
6. Update labels as needed

Report what you changed and why." --allowedTools 'Bash(gh:*),Read,Glob,Grep'
