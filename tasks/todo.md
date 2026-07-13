# #389 — [P4.3.5] Regenerate endpoint hardcodes enable_distribution=False

**Plan (approved autonomously — no architectural fork).**

## Context
- `regenerate_podcast` (`apps/api/src/routers/generation.py:510-539`) delegates to
  `generate_podcast` with hardcoded `enable_composition=False, enable_distribution=False`.
- After #388 the web generate action requests distribution, but regenerate (API-only,
  no web caller) can never distribute.

## Decision
Mirror `generate_podcast` exactly: same two Query params, same `default=False`.
The issue floated defaulting `enable_distribution=true` on regenerate; rejected —
the generate endpoint defaults to False, and an asymmetric default across the two
endpoints is the exact class of confusion this issue fixes. Callers (web, when it
grows a regenerate button) opt in explicitly, as #388 did for generate.

## Steps (TDD)
1. **RED** — tests:
   - `tests/test_distribution_wiring.py`: `test_regenerate_forwards_platforms_when_distribution_enabled`
     — webhook target + settings patched, POST `/regenerate?enable_distribution=true`,
     assert task kwargs `enable_distribution is True` and platforms mapping present
     (mirrors the existing generate test).
   - `tests/test_regenerate_endpoint.py`: happy path additionally asserts task kwargs
     `enable_distribution is False` by default.
2. **GREEN** — `regenerate_podcast`: add `enable_composition` / `enable_distribution`
   Query params (defaults False, same descriptions), pass through as keyword args
   (keep the keyword-arg delegation comment re: positional misalignment, #213).
3. Quality gate: pytest, ruff, third-party review (opencode/GLM pre-PR + post-PR).
4. PR → demo (Showboat, API-only) → CI gate → docs sync → merge.
