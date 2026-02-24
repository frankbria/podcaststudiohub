# Implementation Prompt for Repo Maintainer

You are implementing GitHub issue #{{ISSUE_NUMBER}} for the Podcastfy Studio Hub repository.

## Your Task

1. **Read the issue**: `gh issue view {{ISSUE_NUMBER}}` — understand what needs to be done.
2. **Read the implementation plan**: Check the issue comments for a triage summary or implementation plan.
3. **Read CLAUDE.md**: Understand project architecture, conventions, and style rules.
4. **Explore the codebase**: Find relevant files, existing patterns, and utilities to reuse.

## Implementation Rules

- Follow TDD: write tests FIRST, then implement until tests pass
- Follow existing code patterns — don't introduce new paradigms
- Python code: PEP 8, tabs for indentation, type hints, docstrings
- TypeScript code: ESLint rules, consistent with existing components
- Keep changes minimal — only modify what's necessary for this issue
- Do NOT add new dependencies unless absolutely required (max 2 per PR)

## Scope Limits

- Maximum {{MAX_LINES}} lines changed
- Maximum {{MAX_FILES}} files changed
- If you need to exceed these limits, STOP and explain why in a comment

## Branch and PR

1. Create branch: `maintainer/issue-{{ISSUE_NUMBER}}-{{SLUG}}`
2. Make your changes with clear, focused commits
3. Run the test suite:
   - Python: `cd apps/api && uv run pytest`
   - TypeScript: `cd apps/web && npm test`
4. Run linters:
   - Python: `cd apps/api && uv run ruff check .`
   - TypeScript: `cd apps/web && npm run lint`
5. Create a PR with:
   - Title: Short description (under 70 chars)
   - Body: Summary of changes, test plan, closes #{{ISSUE_NUMBER}}
   - PR type: {{PR_TYPE}} (normal, draft, or auto-merge)

## PR Body Template

```markdown
## Summary
[1-3 bullet points describing what changed and why]

Closes #{{ISSUE_NUMBER}}

## Changes
- [List of specific changes]

## Test Plan
- [ ] Unit tests added/updated
- [ ] Existing tests pass
- [ ] Manual verification: [describe what to check]

---
*Automated by repo-maintainer ({{TIER}})*
```

## If You Get Stuck

- If tests fail and you can't fix them after 2 attempts: create the PR as a draft with a comment explaining the failure
- If the issue is ambiguous: create a draft PR with what you have and add a comment asking for clarification
- If scope exceeds limits: stop, comment on the issue explaining why, and create a draft PR with partial work
