# #494 — Next's agent-rules block lives in AGENTS.md, not CLAUDE.md

*2026-10-13T16:13:28Z by Showboat 0.6.1*
<!-- showboat-id: 6d2c0e50-8c92-45ca-8c42-af4611ee6a84 -->

Owner decision (2026-10-13): **AGENTS.md hosts it.** Under an AI agent (`@vercel/detect-agent`, e.g. `AI_AGENT`), `next dev` runs `ensureAgentRulesForDev`. That skips when the rules are current and otherwise calls `writeAgentFiles`, which prefers `AGENTS.md` when it exists and `CLAUDE.md` does not carry the block. `/tmp/demo_494.js` runs those exact Next functions (16.3.4, from `node_modules`) on a copy of a directory's agent files. A live `next dev` is not used here because Turbopack rejects the worktree's symlinked `node_modules`.

`main` (no `AGENTS.md`):

```bash
M=$(mktemp -d); git show main:apps/web/CLAUDE.md > $M/CLAUDE.md; node /tmp/demo_494.js $M .; rm -rf $M
```

```output
AGENTS.md present: false
next dev would: {"agentsMd":"skipped","claudeMd":"updated"}
CLAUDE.md changed: true
```

This branch:

```bash
node /tmp/demo_494.js . .
```

```output
AGENTS.md present: true
next dev would: rules already current: nothing written
CLAUDE.md changed: false
```

On `main`, an agent-run `next dev` rewrites `CLAUDE.md` (the dirty tree from PR #492). With `AGENTS.md` committed, the rules are already current, nothing is written, and `CLAUDE.md` is never touched. On a Next upgrade that changes the block, `writeAgentFiles` updates `AGENTS.md` (verified: it reports `claudeMd: skipped`). `apps/web/CLAUDE.md` now says so where a developer will look.
