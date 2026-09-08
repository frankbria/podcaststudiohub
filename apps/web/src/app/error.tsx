"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

/**
 * Route-level error boundary. Without one, any throw during a client render
 * escapes to Next's built-in handler and the route dies at the browser level
 * ("This page couldn't load") — which is how the #481 signup crash presented,
 * and why it read as a missing error message rather than a dead page.
 *
 * This does not excuse the throw; it bounds the blast radius to one route and
 * leaves the user a way out.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // apps/web has NO client error telemetry: Sentry is wired for the API and the
    // Celery worker only (deployment/README.md, "Error tracking — issue #320"),
    // and there is no client instrumentation file here. So this lands in the
    // user's own browser console and nowhere else — until reporting is wired up,
    // a digest quoted in a bug report cannot be correlated with anything.
    console.error("Route render error:", error)
  }, [error])

  return (
    <main id="main-content" className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Something went wrong</CardTitle>
          <CardDescription>
            This page hit an unexpected error. Trying again often clears it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/*
            The message is framework/library chatter ("Objects are not valid as a
            React child…"), useful while developing and noise to an end user, so
            production sees the digest instead — that is what a bug report needs.
          */}
          <div role="alert" aria-live="assertive" className="text-destructive text-sm">
            {process.env.NODE_ENV === "production"
              ? "The page could not be displayed."
              : error.message || "Unknown error"}
          </div>
          {error.digest && (
            <p className="text-muted-foreground text-xs">
              Reference: <code>{error.digest}</code>
            </p>
          )}
          <Button onClick={reset} className="w-full">
            Try again
          </Button>
        </CardContent>
      </Card>
    </main>
  )
}
