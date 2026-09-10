"use client"

import { useEffect } from "react"
import { ErrorFallback } from "@/components/ErrorFallback"
import { reportClientError } from "@/lib/report-client-error"

/**
 * Route-level error boundary. Without one, any throw during a client render
 * escapes to Next's built-in handler and the route dies at the browser level
 * ("This page couldn't load") — which is how the #481 signup crash presented,
 * and why it read as a missing error message rather than a dead page.
 *
 * This does not excuse the throw; it bounds the blast radius to one route and
 * leaves the user a way out.
 *
 * A throw in `app/layout.tsx` itself bypasses this boundary — that is what
 * `app/global-error.tsx` is for.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error("Route render error:", error)
    // Reports to the same Sentry project as the API, so the digest rendered
    // below can actually be looked up (issue #485, item 3). No DSN configured
    // means the relay no-ops, matching init_sentry() on the backend.
    reportClientError(error, "route-error")
  }, [error])

  return <ErrorFallback error={error} reset={reset} />
}
