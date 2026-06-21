# Issue #234 — IP-pin outbound fetches (DNS-rebinding SSRF residual)

Follow-up to #206. `validate_public_url` resolves the host and rejects non-public
IPs, but `requests`/`httpx` **re-resolve** at connect time → TOCTOU DNS-rebinding
window. Fix: pin the connection to the IP the guard already validated, while
keeping the original `Host` header, SNI, and cert verification against the hostname.

`validate_public_url` already **returns** the list of resolved public IPs — pin to `resolved[0]`.

## Plan

### 1. New helper: `apps/api/src/utils/pinned_fetch.py`
- `pinned_session(url, ip) -> requests.Session`: a `Session` with a `_PinnedIPAdapter`
  mounted for the URL's scheme. The adapter:
  - rewrites the request URL host → `ip` (IPv6-bracketed, port preserved),
  - keeps `Host: <original host[:port]>`,
  - for https, sets urllib3 `server_hostname` + `assert_hostname` = hostname on the
    pool (SNI + cert verified against the hostname, not the IP).
- `pin_httpx(url, ip) -> (pinned_url, headers, extensions)`: returns the IP URL,
  `{"Host": host}`, and `{"sni_hostname": host}` (httpx verifies TLS against the host).
- `_ip_netloc(ip, port)` helper (IPv6 bracketing + optional port).

### 2. `content_extraction_service.py` `_fetch_and_extract_safely` (requests.get)
- Capture `resolved = validate_public_url(...)` (already strict, non-empty).
- Fetch via `with pinned_session(current_url, resolved[0]) as s: s.get(...)`.

### 3. `tasks/platform_distribution.py` `_distribute_via_webhook` (requests.post/get)
- Capture `resolved` from the existing strict `validate_public_url(...)`.
- Issue POST/GET through `pinned_session(webhook_url, resolved[0])`.

### 4. `services/source_validator_service.py` `_check_url_accessibility` (httpx.head)
- Make `_validate_url_not_internal` return the resolved IP list.
- Validate at the **top of the loop** for `current_url` (covers first hop + every
  redirect hop), capture IPs, and `client.head(pin_httpx(current_url, ips[0]))`.
- Remove now-redundant per-hop re-validation block.

## Tests
- `tests/unit/test_pinned_fetch.py`: `_ip_netloc` (v4/v6/port); `pinned_session.send`
  rewrites URL→IP + preserves Host + carries server_hostname/assert_hostname on the
  pool; `pin_httpx` output shape.
- Rebinding proof (per AC#3): patch `socket.getaddrinfo` to return public IP at
  validation then private IP on any later call; patch urllib3's
  `util.connection.create_connection` chokepoint to capture the connect target;
  assert the socket connects to the **validated public IP** (an IP literal → no
  re-resolution), never the rebind private IP. Mirror for the httpx HEAD path.
- Existing SSRF/extraction/webhook tests stay green.

## Acceptance criteria
- [ ] Content-extraction + webhook fetches connect only to the guard-validated IP (no re-resolution window).
- [ ] TLS verification still works for HTTPS targets.
- [ ] Rebinding test (guard sees public IP, connect would get private IP) is blocked.

## Design notes
- No process-wide `getaddrinfo` monkeypatching (issue's explicit constraint) —
  pinning is per-connection/per-request, safe under Celery/threadpool concurrency.
- No new dependencies (requests/httpx/urllib3 already present).
- Plan source: issue body "Proposed fix" (no separate plan comment).
