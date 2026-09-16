# Mutation report: #492 error boundaries and `/api/monitoring` relay (issue #493)

PR #492 added four test files. Their mutation-testing pass was abandoned mid-run
(the agent corrupted the tree), so the tests had never been shown to fail when
the behaviour they name is broken. This is that pass, completed 2026-09-16.

Re-run from `apps/web` in a clean worktree (it edits source files in place and
restores them; nothing else may be editing the tree):

```sh
node scripts/mutation-check-492.mjs        # exit 1 if any mutation survives
node scripts/mutation-check-492.mjs route  # only mutations whose name contains "route"
```

## Run 1 — tests as merged in #492

| # | Mutation | Result | Failing test(s) |
|---|---|---|---|
| 1 | route: remove `if (!dsn) return 204` gate | **SURVIVED** | — |
| 2 | route: envelope header event_id differs from event's | KILLED | `tags the event with the digest so error.tsx references are searchable` |
| 3 | route: drop the `exception` field | KILLED | `sends the message as the exception value so Sentry groups by it`<br>`truncates oversized fields rather than relaying them` |
| 4 | route: remove the truncation `.slice()` in str() | KILLED | `truncates oversized fields rather than relaying them` |
| 5 | route: str() coerces with String() instead of dropping | KILLED | `coerces non-string fields instead of relaying attacker-shaped values` |
| 6 | route: remove the Content-Length pre-check | KILLED | `rejects an oversized Content-Length before reading the body` |
| 7 | route: remove the Sec-Fetch-Site gate | KILLED | `rejects a cross-site POST, which CORS would not stop` |
| 8 | route: drop the `fingerprint` | KILLED | `fingerprints by digest so redacted production errors do not collapse` |
| 9 | route: remove the `!ingest.ok` check | KILLED | `logs a non-2xx from Sentry instead of reporting success` |
| 10 | report-client-error: keepalive true → false | KILLED | `posts the message, stack and digest to the same-origin relay` |
| 11 | report-client-error: send location.href instead of pathname | KILLED | `sends the pathname only, never the query string` |
| 12 | report-client-error: remove the try/catch | KILLED | `does not throw when fetch is unavailable` |
| 13 | report-client-error: remove the truncation | KILLED | `truncates message and stack, which Chrome would otherwise reject wholesale` |
| 14 | report-client-error: change the URL | KILLED | `posts the message, stack and digest to the same-origin relay` |
| 15 | global-error: return the fallback without <html>/<body> | KILLED | `renders its own html and body, since the root layout is gone` |
| 16 | global-error: remove the reportClientError call | KILLED | `reports the error to the relay so a layout crash is not invisible` |
| 17 | error: remove the reportClientError call | KILLED | `reports the error to the relay so the digest is searchable in Sentry` |

16/17 killed. The survivor: with the `if (!dsn) return 204` gate removed, an
unset DSN falls into `envelopeUrl(undefined)`, which throws inside its
`try`, returns `null`, and the "SENTRY_DSN is set but not parseable" branch
answers 204 too — but logs an error on every client crash. The test asserted
only the 204 and the absent fetch, so it could not tell the hard no-op from the
noisy one.

## Fix

`__tests__/app/api/monitoring/route.test.ts`, "no-ops with 204 and sends
nothing when SENTRY_DSN is unset": added `expect(consoleError).not.toHaveBeenCalled()`.

## Run 2 — after the fix

| # | Mutation | Result | Failing test(s) |
|---|---|---|---|
| 1 | route: remove `if (!dsn) return 204` gate | KILLED | `no-ops with 204 and sends nothing when SENTRY_DSN is unset` |
| 2 | route: envelope header event_id differs from event's | KILLED | `tags the event with the digest so error.tsx references are searchable` |
| 3 | route: drop the `exception` field | KILLED | `sends the message as the exception value so Sentry groups by it`<br>`truncates oversized fields rather than relaying them` |
| 4 | route: remove the truncation `.slice()` in str() | KILLED | `truncates oversized fields rather than relaying them` |
| 5 | route: str() coerces with String() instead of dropping | KILLED | `coerces non-string fields instead of relaying attacker-shaped values` |
| 6 | route: remove the Content-Length pre-check | KILLED | `rejects an oversized Content-Length before reading the body` |
| 7 | route: remove the Sec-Fetch-Site gate | KILLED | `rejects a cross-site POST, which CORS would not stop` |
| 8 | route: drop the `fingerprint` | KILLED | `fingerprints by digest so redacted production errors do not collapse` |
| 9 | route: remove the `!ingest.ok` check | KILLED | `logs a non-2xx from Sentry instead of reporting success` |
| 10 | report-client-error: keepalive true → false | KILLED | `posts the message, stack and digest to the same-origin relay` |
| 11 | report-client-error: send location.href instead of pathname | KILLED | `sends the pathname only, never the query string` |
| 12 | report-client-error: remove the try/catch | KILLED | `does not throw when fetch is unavailable` |
| 13 | report-client-error: remove the truncation | KILLED | `truncates message and stack, which Chrome would otherwise reject wholesale` |
| 14 | report-client-error: change the URL | KILLED | `posts the message, stack and digest to the same-origin relay` |
| 15 | global-error: return the fallback without <html>/<body> | KILLED | `renders its own html and body, since the root layout is gone` |
| 16 | global-error: remove the reportClientError call | KILLED | `reports the error to the relay so a layout crash is not invisible` |
| 17 | error: remove the reportClientError call | KILLED | `reports the error to the relay so the digest is searchable in Sentry` |

17/17 killed.
