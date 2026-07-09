# #305 — SSRF-harden webhook test-connection (in progress)

**Plan source**: CodeRabbit plan comment on issue, verified against code 2026-07-09.
**Branch**: `fix/issue-305-webhook-test-ssrf`

## Verified facts
- `_test_webhook_connection` (distribution_target_service.py:625) fires raw `httpx.AsyncClient` from the stored URL — no re-validation, no pinning, default redirect handling.
- `validate_public_url(url, *, allowed_schemes, allowed_ports, block_on_resolution_failure)` → `List[str]` of resolved public IPs; raises `SSRFValidationError` (src/utils/ssrf.py:88).
- `pin_httpx(url, ip)` → `(pinned_url, {"Host": netloc}, {"sni_hostname": hostname})` (src/utils/pinned_fetch.py:91). Async httpx usage pattern proven in source_validator_service.py:148.
- Existing test `test_webhook_connection_test_with_encrypted_headers` uses `hooks.example.com` — must patch `validate_public_url` after the change (adaptation, not weakening).

## Steps
- [x] Branch `fix/issue-305-webhook-test-ssrf`
- [ ] TDD RED: internal URL → success=False + httpx never called; public target → pinned URL, Host/SNI preserved, `follow_redirects=False`; update existing encrypted-headers test to patch `validate_public_url`
- [ ] GREEN: in `_test_webhook_connection`, call `validate_public_url(url, allowed_schemes=("https",), allowed_ports={443}, block_on_resolution_failure=True)`; catch `SSRFValidationError` → standard failure dict; `pin_httpx(url, resolved[0])`; merge pinned Host into decrypted headers; pass extensions; `follow_redirects=False`
- [ ] Deslop → quality gate (opencode pre-PR review) → PR → post-PR review → demo (hard gate) → CI gate → docs sync → merge

## Acceptance criteria (issue #305)
- [ ] Re-validate with `validate_public_url(url, allowed_schemes=('https',), allowed_ports={443}, block_on_resolution_failure=True)` immediately before the request
- [ ] Pin to the validated IP (mirror `_distribute_via_webhook` / httpx pattern)
- [ ] `follow_redirects=False`
