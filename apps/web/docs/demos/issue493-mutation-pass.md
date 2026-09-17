# Issue #493: the #492 mutation pass, completed and re-runnable

*2026-09-16T22:13:07Z*

PR #492 added four test files (error boundaries + the /api/monitoring relay). Their mutation pass was abandoned mid-run, so none had been shown to fail when the behaviour it names is broken. Criterion 1: every mutation from the issue is applied to the implementation, the matching test file run, and the result recorded. The driver does exactly that — baseline first, then each mutation, restoring the source after every run.

```bash
node scripts/mutation-check-492.mjs > /tmp/mut-full.txt 2>&1; echo "exit=$?"; tail -22 /tmp/mut-full.txt
```

```output
exit=0
KILLED   error: remove the reportClientError call  [Tests:       1 failed, 5 passed, 6 total]
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

17/17 killed, 0 survived
```

Outcome: 17/17 killed, exit 0, and the failing-test column names which test caught each one. The source files are untouched afterwards:

```bash
git status --short -- src __tests__ && echo "(clean)"
```

```output
(clean)
```

Criterion 2: an assertion is added wherever no test failed. Run 1 (see docs/mutation-report-492.md) found one survivor — removing the SENTRY_DSN gate — because the unparseable-DSN branch also answers 204 with no fetch. This is the whole test change on the branch:

```bash
git diff main -- __tests__/app/api/monitoring/route.test.ts
```

```output
diff --git a/apps/web/__tests__/app/api/monitoring/route.test.ts b/apps/web/__tests__/app/api/monitoring/route.test.ts
index 30c5f1f..9edc258 100644
--- a/apps/web/__tests__/app/api/monitoring/route.test.ts
+++ b/apps/web/__tests__/app/api/monitoring/route.test.ts
@@ -64,11 +64,16 @@ describe('POST /api/monitoring', () => {

   it('no-ops with 204 and sends nothing when SENTRY_DSN is unset', async () => {
     delete process.env.SENTRY_DSN
+    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})

     const response = await POST(makeRequest({ message: 'boom' }))

     expect(response.status).toBe(204)
     expect(fetchMock).not.toHaveBeenCalled()
+    // Silent, not just 204: without the gate an unset DSN falls through to the
+    // "set but not parseable" branch, which also answers 204 but logs an error
+    // on every client crash. That is the mutation #493 found surviving.
+    expect(consoleError).not.toHaveBeenCalled()
   })

   it('no-ops with 204 when SENTRY_DSN is not a parseable DSN', async () => {
```

Proof that this line is what kills it: delete the added assertion, re-run only the gate mutation, and it survives again (exit 1). Then restore the test.

```bash
sed -i "/expect(consoleError).not.toHaveBeenCalled()/d" __tests__/app/api/monitoring/route.test.ts; node scripts/mutation-check-492.mjs gate > /tmp/mut-gate.txt 2>&1; echo "exit=$?"; tail -6 /tmp/mut-gate.txt; git checkout -- __tests__/app/api/monitoring/route.test.ts; git status --short -- __tests__ && echo "(test restored)"
```

```output
exit=1
| # | Mutation | Result | Failing test(s) |
|---|---|---|---|
| 1 | route: remove `if (!dsn) return 204` gate | SURVIVED | — |
| 2 | route: remove the Sec-Fetch-Site gate | KILLED | `rejects a cross-site POST, which CORS would not stop` |

1/2 killed, 1 survived
(test restored)
```

The codex review of this branch found that a red baseline would count as "all killed". The driver now runs each test file unmodified first and aborts with exit 2 instead of reporting a mutation result. Break a test on purpose:

```bash
sed -i "s/toBe(202)/toBe(299)/" __tests__/app/api/monitoring/route.test.ts; node scripts/mutation-check-492.mjs gate > /tmp/mut-base.txt 2>&1; echo "exit=$?"; head -1 /tmp/mut-base.txt; echo "KILLED rows: $(grep -c KILLED /tmp/mut-base.txt)"; git checkout -- __tests__/app/api/monitoring/route.test.ts; git status --short -- __tests__ && echo "(test restored)"
```

```output
exit=2
BASELINE FAILED for __tests__/app/api/monitoring/route.test.ts — not a mutation result, aborting.
KILLED rows: 0
(test restored)
```

Exit 2, no KILLED rows: a broken suite cannot masquerade as a passed mutation check.
