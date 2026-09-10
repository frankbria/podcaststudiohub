/**
 * Server-side half of the client error relay (issue #485, item 3).
 *
 * `apps/web` had no error telemetry at all: Sentry was wired for the API and the
 * Celery worker only, so a production render crash — the #481 class — was
 * reported nowhere and the digest shown by `error.tsx` had nothing to be looked
 * up against. This handler closes that: boundaries POST here same-origin and the
 * event is forwarded to the SAME Sentry project as the backend.
 *
 * Deliberately not `@sentry/nextjs`. The relay is ~80 lines, adds no dependency
 * to the npm-audit surface, keeps the DSN off the client, and needs no
 * `connect-src` exception in the nonce/strict-dynamic CSP (issue #307). The cost
 * is no source maps, breadcrumbs or performance data — grouping is by message,
 * and the digest is a searchable tag. If those turn out to be needed, the
 * upgrade path is the official SDK.
 *
 * The DSN gate copies `init_sentry()` in `apps/api/src/logging_config.py`: no
 * DSN means a hard no-op, so local dev and CI never phone home and need no
 * opt-out.
 */

// Caps. A public unauthenticated endpoint must not relay whatever it is handed:
// oversized bodies are rejected before parsing, and oversized fields are
// truncated rather than forwarded.
const MAX_BODY_BYTES = 64 * 1024
const MAX_MESSAGE = 1024
const MAX_STACK = 8192
const MAX_TAG = 200

/** `https://<key>@<host>/<path…>/<projectId>` -> the envelope ingest URL. */
function envelopeUrl(dsn: string): string | null {
  try {
    const { protocol, host, username, pathname } = new URL(dsn)
    const segments = pathname.split("/").filter(Boolean)
    const projectId = segments.pop()
    if (!username || !projectId) return null
    const prefix = segments.length > 0 ? `/${segments.join("/")}` : ""
    return `${protocol}//${host}${prefix}/api/${projectId}/envelope/?sentry_key=${username}&sentry_version=7`
  } catch {
    return null
  }
}

/** Anything not a usable string is dropped, not coerced into `[object Object]`. */
function str(value: unknown, max: number): string | undefined {
  if (typeof value !== "string" || value.length === 0) return undefined
  return value.slice(0, max)
}

export async function POST(request: Request): Promise<Response> {
  const dsn = process.env.SENTRY_DSN
  if (!dsn) return new Response(null, { status: 204 })

  const url = envelopeUrl(dsn)
  if (!url) {
    console.error("[monitoring] SENTRY_DSN is set but not parseable — dropping client error")
    return new Response(null, { status: 204 })
  }

  // Content-Length first: `request.text()` buffers the whole body into memory,
  // so checking the cap only after reading would let an unauthenticated caller
  // pick the allocation size. A chunked request without the header still gets
  // read, hence the second check.
  const declared = Number(request.headers.get("content-length"))
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
    return new Response(null, { status: 413 })
  }

  const raw = await request.text()
  if (raw.length > MAX_BODY_BYTES) return new Response(null, { status: 413 })

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return new Response(null, { status: 400 })
  }

  const report = (body ?? {}) as Record<string, unknown>
  const message = str(report.message, MAX_MESSAGE)
  if (!message) return new Response(null, { status: 400 })

  const eventId = crypto.randomUUID().replace(/-/g, "")
  const sentAt = new Date().toISOString()

  const tags: Record<string, string> = {}
  const digest = str(report.digest, MAX_TAG)
  const context = str(report.context, MAX_TAG)
  if (digest) tags.digest = digest
  if (context) tags.context = context

  const event = {
    event_id: eventId,
    timestamp: Date.now() / 1000,
    platform: "javascript",
    level: "error",
    logger: "apps/web",
    environment: process.env.SENTRY_ENVIRONMENT ?? process.env.NODE_ENV ?? "development",
    tags,
    // Grouping is by this value: without source maps the frames would be
    // minified noise, so the stack rides along as context rather than as a
    // parsed stacktrace that Sentry would try (and fail) to symbolicate.
    exception: { values: [{ type: "Error", value: message }] },
    extra: {
      stack: str(report.stack, MAX_STACK),
      pathname: str(report.pathname, MAX_TAG),
    },
  }

  const envelope =
    `${JSON.stringify({ event_id: eventId, sent_at: sentAt })}\n` +
    `${JSON.stringify({ type: "event" })}\n` +
    `${JSON.stringify(event)}\n`

  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-sentry-envelope" },
      body: envelope,
    })
  } catch (error) {
    // Ingest being down must not turn into a second error in the browser, which
    // is already rendering a crash screen.
    console.error("[monitoring] failed to forward client error to Sentry:", error)
  }

  return new Response(null, { status: 202 })
}
