/**
 * Same-origin API proxy for authenticated backend calls.
 *
 * The backend access token lives only in the server-side NextAuth JWT (an
 * httpOnly cookie) and is never exposed to browser JavaScript. Client code calls
 * this proxy with a relative path (e.g. `/api/proxy/projects`); the handler reads
 * the token via `getToken` and injects it as an `Authorization: Bearer` header
 * when forwarding to the backend.
 *
 * Because the token is added server-side and the request never carries it in a
 * URL/query string, it cannot leak into proxy/access logs, browser history, or
 * Referer headers. The same handler streams Server-Sent Events back to the
 * browser's EventSource, which cannot set an Authorization header itself
 * (issue #212).
 */
import { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'

function getApiBaseUrl(): string {
  return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
}

// Request headers that must not be forwarded to the backend: hop-by-hop headers,
// length/encoding headers (recomputed by fetch), the browser cookie (the backend
// authenticates via the injected Bearer token, not the NextAuth session cookie),
// and any client-supplied Authorization (we set our own from the server token).
const STRIP_REQUEST_HEADERS = new Set([
  'host',
  'connection',
  'content-length',
  'accept-encoding',
  'cookie',
  'authorization',
])

// Response headers that must be dropped: the body is re-framed by the runtime,
// so stale length/encoding headers would corrupt it.
const STRIP_RESPONSE_HEADERS = ['content-encoding', 'content-length', 'transfer-encoding']

async function handler(
  req: NextRequest,
  ctx: { params: Promise<{ path?: string[] }> }
): Promise<Response> {
  // getToken's `req` union comes from next-auth's bundled next/server types,
  // which are structurally identical but a distinct instance from ours; the cast
  // bridges that mismatch without weakening the rest of the handler's typing.
  const token = await getToken({
    req: req as unknown as Parameters<typeof getToken>[0]['req'],
    secret: process.env.NEXTAUTH_SECRET,
  })
  const accessToken = token?.accessToken as string | undefined

  if (!accessToken) {
    return new Response(JSON.stringify({ detail: 'Not authenticated' }), {
      status: 401,
      headers: { 'content-type': 'application/json' },
    })
  }

  const { path = [] } = await ctx.params
  const search = req.nextUrl.search // includes the leading "?" or is empty
  const targetUrl = `${getApiBaseUrl()}/${path.map(encodeURIComponent).join('/')}${search}`

  const headers = new Headers()
  req.headers.forEach((value, key) => {
    if (!STRIP_REQUEST_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value)
    }
  })
  headers.set('Authorization', `Bearer ${accessToken}`)

  const hasBody = req.method !== 'GET' && req.method !== 'HEAD'
  const body = hasBody ? await req.arrayBuffer() : undefined

  const upstream = await fetch(targetUrl, {
    method: req.method,
    headers,
    body,
    redirect: 'manual',
    cache: 'no-store',
  })

  const responseHeaders = new Headers(upstream.headers)
  for (const name of STRIP_RESPONSE_HEADERS) {
    responseHeaders.delete(name)
  }

  // Returning the upstream body (a ReadableStream) streams JSON and SSE alike.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export const GET = handler
export const POST = handler
export const PUT = handler
export const PATCH = handler
export const DELETE = handler

// Never statically optimize: this proxy is per-request and may stream SSE.
export const dynamic = 'force-dynamic'
