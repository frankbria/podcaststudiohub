"use client"

import { useEffect } from "react"
import "./globals.css"
import { ErrorFallback } from "@/components/ErrorFallback"
import { reportClientError } from "@/lib/report-client-error"

/**
 * Boundary of last resort (issue #485, item 2).
 *
 * `app/error.tsx` catches throws inside a route, but a throw in
 * `app/layout.tsx` itself happens *above* it and bypasses it entirely — so
 * before this file existed a layout crash still produced the browser's own
 * "This page couldn't load", the exact failure #481 was about.
 *
 * This replaces the root layout when it fires, so it owns the `<html>`/`<body>`
 * tags and imports the stylesheet itself: neither is inherited from a layout
 * that just failed to render.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error("Root layout render error:", error)
    reportClientError(error, "global-error")
  }, [error])

  return (
    <html lang="en">
      <body>
        <ErrorFallback error={error} reset={reset} />
      </body>
    </html>
  )
}
