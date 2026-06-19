# Issue #224 — Harden agentic/CI workflows

Security hardening of GitHub Actions workflows. Plan source: issue body (acceptance criteria).

## Steps

### 1. Stop interpolating untrusted input into `run:` shells
- **rm-loop.yml** (line ~146): issue `title` is interpolated into a `run:` shell → shell injection.
  Move `title` (and the dispatch input `force_issue`) into step-level `env:` and reference `"$TITLE"` / `"$FORCE_ISSUE"`.
- **playwright-tests.yml** (line ~88): `github.event.inputs.test_suite` (choice input, arbitrary via API) interpolated into a `run:` glob.
  Move to `env:` and reference `"$TEST_SUITE"` (keep the surrounding `*` globs unquoted).

### 2. Pin third-party actions to full commit SHAs
- `anthropics/claude-code-action@v1` → `@51705da45eecce209d4700538bf8377d5b5fc695` across 6 workflows
  (rm-loop, rm-review, rm-docs, rm-refine, rm-research, claude).
- Each pin gets a `# vX.Y` comment so Dependabot can track it.
- First-party `actions/*` (checkout, setup-node, etc.) left on tags — not flagged, Dependabot covers them.
- `draft-pdf.yml` (the other flagged pins: `openjournals-draft-action@master`,
  `create-pull-request@v5`) was **deleted** instead — dead leftover from the
  upstream JOSS-paper fork (no `paper/` dir; failing on main since Nov 2025).

### 3. Add Dependabot for github-actions
- New `.github/dependabot.yml` with the `github-actions` ecosystem (weekly).

### 4. Protect the deploy secret (deploy-dev.yml)
- `chmod 600` the `.env.production` file after writing `NEXTAUTH_SECRET` into it.
- Remove `NEXTAUTH_SECRET` from the PM2 command line (argv → visible via `ps`); Next.js reads it from `.env.production` at runtime.

### 5. (Judgment call) Human approval before auto-merge to main
- rm-review.yml `auto-merge` job currently merges every tier once CI + verification pass.
- Add `environment: auto-merge-approval` to that job so a required-reviewer rule can gate it.
- Takes effect only once reviewers are configured on that environment in repo settings (no-op otherwise).

## Acceptance criteria
- [ ] Untrusted issue title / dispatch inputs passed via `env:`, referenced as `"$VAR"`; no `${{ }}` interpolation into `run:`.
- [ ] Third-party actions pinned to full SHAs (no `@master`); Dependabot enabled for github-actions.
- [ ] Deploy secret written to a chmod-600 env file; not passed on argv.
- [ ] Auto-merge to main can require human approval (environment gate).

## Verification
- `actionlint` on changed workflows (syntax + shellcheck of `run:` blocks).
- grep assertion: no untrusted `${{ }}` left inside `run:` blocks of the touched workflows.
- No test framework exists for workflow YAML — verification is actionlint + targeted grep + demo gate.
