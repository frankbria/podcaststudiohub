"use client"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

/**
 * The screen both error boundaries render — `app/error.tsx` (route throws) and
 * `app/global-error.tsx` (root-layout throws). Shared so the two cannot drift:
 * a layout crash is the rarer path and would be the one to rot.
 */
export function ErrorFallback({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
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
