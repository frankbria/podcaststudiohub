#!/usr/bin/env bash
# local-loop.sh — Mode B: Run the implementation loop locally via Claude Code.
# This wraps the same config/state/circuit-breaker logic as rm-loop.yml
# but invokes Claude Code locally with full skill/agent access.
#
# Usage:
#   ./local-loop.sh              # Auto-select next issue
#   ./local-loop.sh 42           # Force implement issue #42
#   ./local-loop.sh --dry-run    # Select issue but don't implement
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
CONFIG="$REPO_ROOT/.github/repo-maintainer/config.yml"
STATE="$REPO_ROOT/.github/repo-maintainer/state.json"

DRY_RUN=false
FORCE_ISSUE=""

for arg in "$@"; do
	case "$arg" in
		--dry-run) DRY_RUN=true ;;
		[0-9]*) FORCE_ISSUE="$arg" ;;
	esac
done

# ── Step 1: Circuit Breaker Check ───────────────────
echo "=== Circuit Breaker Check ==="
CB_RESULT=$("$SCRIPT_DIR/check-circuit-breakers.sh" 2>&1) || {
	REASON=$(echo "$CB_RESULT" | jq -r '.reason // "unknown"')
	echo "Circuit breaker tripped: $REASON"
	exit 0
}
MODE=$(echo "$CB_RESULT" | jq -r '.mode')
echo "Mode: $MODE — all checks passed"

# ── Step 2: Select Issue ───────────────────────────
echo ""
echo "=== Issue Selection ==="
if [[ -n "$FORCE_ISSUE" ]]; then
	ISSUE_RESULT=$("$SCRIPT_DIR/select-next-issue.sh" "$FORCE_ISSUE")
else
	ISSUE_RESULT=$("$SCRIPT_DIR/select-next-issue.sh") || {
		echo "No eligible issues found."
		exit 0
	}
fi

ISSUE_NUMBER=$(echo "$ISSUE_RESULT" | jq -r '.issue_number')
ISSUE_TITLE=$(echo "$ISSUE_RESULT" | jq -r '.title')
TIER=$(echo "$ISSUE_RESULT" | jq -r '.tier')

echo "Selected: #$ISSUE_NUMBER — $ISSUE_TITLE ($TIER)"

if [[ "$DRY_RUN" == "true" ]]; then
	echo ""
	echo "=== Dry Run Complete ==="
	echo "$ISSUE_RESULT" | jq .
	exit 0
fi

# ── Step 3: Determine Skill ────────────────────────
USE_SKILL=$(yq -r '.local.use_skill // "implementing-issue-plans"' "$CONFIG")
echo ""
echo "=== Implementing with skill: $USE_SKILL ==="

# ── Step 4: Invoke Claude Code ─────────────────────
MAX_LINES=$(yq -r ".limits.${MODE}.max_lines_per_pr // 500" "$CONFIG")
MAX_FILES=$(yq -r ".limits.${MODE}.max_files_per_pr // 15" "$CONFIG")

case "$TIER" in
	T0) PR_TYPE="auto-merge" ;;
	T1) PR_TYPE="normal" ;;
	T2|T3) PR_TYPE="draft" ;;
	*) PR_TYPE="normal" ;;
esac

# Run Claude Code with the implementing-issue-plans skill
claude -p "Implement GitHub issue #${ISSUE_NUMBER} using the /${USE_SKILL} skill.

Context:
- Governance tier: $TIER (PR type: $PR_TYPE)
- Max lines: $MAX_LINES, max files: $MAX_FILES
- Operating mode: $MODE
- Branch naming: maintainer/issue-${ISSUE_NUMBER}-<slug>

Read the issue, follow TDD, implement, and create a ${PR_TYPE} PR.
Add footer: 'Automated by repo-maintainer ($TIER, local mode)'" --allowedTools 'Bash,Read,Write,Edit,Glob,Grep,Skill'

RESULT=$?

# ── Step 5: Update State ───────────────────────────
echo ""
echo "=== Updating State ==="

# Find PR number
PR_NUMBER=$(gh pr list --search "maintainer/issue-${ISSUE_NUMBER}" --state open --json number --limit 1 --jq '.[0].number // 0' 2>/dev/null || echo "0")

if [[ "$RESULT" -eq 0 && "$PR_NUMBER" -gt 0 ]]; then
	"$SCRIPT_DIR/update-state.sh" record-run "$ISSUE_NUMBER" "$PR_NUMBER" "success" "2.00"
	echo "Success: PR #$PR_NUMBER created for issue #$ISSUE_NUMBER"
else
	"$SCRIPT_DIR/update-state.sh" record-run "$ISSUE_NUMBER" "0" "failure" "1.00"
	echo "Implementation failed or no PR created for issue #$ISSUE_NUMBER"
fi

# Commit state changes
cd "$REPO_ROOT"
git add .github/repo-maintainer/state.json
git diff --staged --quiet || {
	git commit -m "chore(maintainer): update state after issue #${ISSUE_NUMBER} (local)"
	echo "State committed."
}
