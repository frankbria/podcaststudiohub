/**
 * Client-side half of the error relay (issue #485, item 3).
 *
 * The browser never sees a Sentry DSN. Error boundaries POST here, same-origin,
 * and `/api/monitoring` forwards a Sentry envelope using the server-side
 * `SENTRY_DSN` that the API and Celery worker already read. Two consequences
 * worth keeping:
 *
 *   - the strict-dynamic CSP in `middleware.ts` needs no change, because
 *     `connect-src 'self'` already covers a same-origin POST; and
 *   - the DSN stays out of the client bundle, unlike a browser SDK's
 *     NEXT_PUBLIC_ DSN.
 */
export function reportClientError(
  error: Error & { digest?: string },
  context: "route-error" | "global-error"
): void {
  // Never let reporting break the boundary that is already rendering an error:
  // the boundary is the last thing standing between the user and a white screen.
  try {
    void fetch("/api/monitoring", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The boundary often renders while the user is navigating away, and a
      // plain fetch would be cancelled along with the document.
      keepalive: true,
      body: JSON.stringify({
        message: error.message,
        stack: error.stack,
        digest: error.digest,
        context,
        // pathname only, never search: query strings here carry callbackUrl and
        // other request-shaped values, and the API's Sentry runs with
        // send_default_pii=False. The client half matches that.
        pathname: window.location.pathname,
      }),
    }).catch(() => {})
  } catch {
    // no fetch, or a runtime that refuses it — nothing to do but carry on
  }
}
