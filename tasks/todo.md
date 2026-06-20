# Issue #216 — Stripe webhook signature bypass (security, apps/api)

Plan source: self-authored (no plan comment). Branch: `fix/216-stripe-webhook-signature`

## Vulnerability
`billing_service.process_webhook` falls back to `json.loads(payload)` and processes
events **unsigned** when `webhook_secret`/`sig_header` are absent. Latent today only
because `STRIPE_SECRET_KEY` isn't a Settings field (`extra="ignore"` drops it →
`_stripe_enabled()` always False → early return). Becomes live the moment billing is
enabled.

## Fix 1 — Settings fields (`config.py`, spaces indent)
- Add `STRIPE_SECRET_KEY: Optional[str] = None` and `STRIPE_WEBHOOK_SECRET: Optional[str] = None`.
- Makes them real, validated Settings (no longer silently dropped). Satisfies AC1.

## Fix 2 — Enforce signature (`billing_service.process_webhook`, tabs indent)
- Keep the `_stripe_enabled()` early-return (`ignored` when billing off) — existing
  behavior/tests rely on it.
- When enabled: **remove the `json.loads` unsigned fallback entirely.**
  - `webhook_secret` or `sig_header` missing → raise `HTTPException(400)` (per AC2).
  - else `construct_event(...)`; on `SignatureVerificationError` → 400 (already present).
- Net: no code path ever parses an unsigned/unverified payload.

## Fix 3 — Tests (`tests/unit/test_billing_unit.py` + `tests/test_billing.py`, tabs)
- enabled + secret set + **missing** sig_header → 400 (AC3).
- enabled + secret set + **invalid** signature (mock `construct_event` raises
  `SignatureVerificationError`) → 400 (AC3).
- enabled + secret set + valid signature → processed.
- Settings exposes `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` (AC1).
- Existing webhook tests (stripe disabled → 200 ignored) remain green.

## Notes / decisions
- AC says "Reject with 400 when secret/sig_header missing." A missing server-side
  `webhook_secret` is arguably a 500 (misconfig), but I follow the AC literally → 400
  for both missing cases. Logged distinctly for ops.
- Scope is small (security hardening) → single agent, TDD.

## Verification
- `uv run pytest tests/test_billing.py tests/unit/test_billing_unit.py`
- Cross-family review (CodeRabbit), demo (Phase 11), CI gate (Phase 12), PR → merge.
