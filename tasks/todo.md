# Open-PR triage — 2026-11-03

Previous plan (#578 / PR #613) is in git history at `810b491`.

## Diagnosis
Every open PR's Quality Gate is red because `main` fails pip-audit: pyasn1 0.6.4 (4 HIGH, fixed 0.6.5)
and dnspython 2.8.0 (1 HIGH, fixed 2.9.0). `review / review` fails on Dependabot PRs only because
Dependabot runs get no `MODEL_API_KEY` secret. The check isn't required (main is unprotected), so ignore it.

## Plan
1. [ ] **Unblock main**: branch `fix/audit-pyasn1-dnspython` that upgrades only pyasn1→0.6.5 and dnspython→2.9.0 in
       `apps/api/uv.lock`. Merge it, then close #693 as superseded.
2. [ ] Rebase the rest onto the fixed main (`@dependabot rebase`, and `gh pr update-branch` for #694).
3. [ ] Merge as each one turns green:
       #694 (glm-review failover, upstream glm-review#17 is merged), #692 boto3, #689 python-dotenv,
       #690 ruff, #688 pymupdf 2.0 (uses `pymupdf` not `fitz`, so the 2.0 changes don't touch us),
       #687 postcss, #686 eslint, #685 tailscale action, #684 claude-code-action.
4. [ ] **#691 google-genai 2.x** = issue #681. Do it on a fresh branch: grpcio 1.84.0 pin, httpx transport
       classification in `src/engine/llm.py`, non-text-part → `ScriptSchemaError`, ms-timeout re-check,
       and a test pinning that `retry_options` stays unset. Live smoke if a working GEMINI key exists.
       Close #691 when the replacement PR merges. Backfill a priority on #681.
5. [ ] **#611 Tailwind 3→4**: this is a migration, not a bump (TS2322 on `darkMode`). Close it with
       `@dependabot ignore this major version`. Retitle #610 as the prioritized Tailwind v4 migration issue.
6. [ ] **#508 TypeScript 7**: typescript-eslint doesn't support TS 7. Close it with
       `@dependabot ignore this major version` and open a prioritized follow-up issue.
