/**
 * App middleware: route protection (issue #222) + nonce-based CSP (issue #307).
 *
 * Route protection — the (auth) route group pages must be gated server-side,
 * before the page renders, not just by the client-side useEffect redirect.
 * Uses getToken (the same session-JWT check next-auth's withAuth runs
 * internally) and reproduces withAuth's /login?callbackUrl=… redirect.
 *
 * CSP — the document Content-Security-Policy carries a fresh per-request nonce
 * and 'strict-dynamic' instead of 'unsafe-inline', so injected inline scripts
 * no longer execute. Next.js reads the policy from the forwarded request
 * header and stamps the nonce onto its own framework/hydration scripts; the
 * root layout reads x-nonce for the theme-flash inline script. nginx no longer
 * sets a document CSP (two CSP headers enforce their intersection, which would
 * block the nonce'd scripts) — see deployment/nginx/podcastfy.conf.
 *
 * Not withAuth: next-auth v4's withAuth skips the signIn page, /api/auth/* and
 * /_next entirely, so a CSP set inside a wrapped middleware would never reach
 * /login — the most exposed unauthenticated page.
 */
import { NextRequest, NextResponse } from 'next/server'
import { getToken } from 'next-auth/jwt'

const PROTECTED_PATHS = ['/dashboard', '/episodes', '/projects']

// media-src / connect-src allow the S3 audio bucket the app streams and
// downloads episode audio from (episodes page + DownloadButton). The host must
// match AWS_S3_BUCKET / AWS_REGION (default us-east-1).
const S3_AUDIO =
  'https://podcaststudiohub-audio.s3.amazonaws.com https://podcaststudiohub-audio.s3.us-east-1.amazonaws.com'

// The signup page fetches ${NEXT_PUBLIC_API_URL}/auth/register from the
// browser. Behind nginx that URL is same-origin ('self' covers it), but in
// dev/CI the API runs on its own port — its origin must be in connect-src or
// signup breaks. Relative/unset URLs have no origin and add nothing.
function apiOrigin(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL ?? '').origin
  } catch {
    return ''
  }
}

function buildCsp(nonce: string): string {
  // React dev tooling (fast refresh) needs eval; production must not allow it.
  const scriptExtra = process.env.NODE_ENV === 'development' ? " 'unsafe-eval'" : ''
  const api = apiOrigin()
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${scriptExtra}`,
    // 'unsafe-inline' stays for styles only: Radix/shadcn set inline style
    // attributes, which style-src nonces cannot cover.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    `media-src 'self' ${S3_AUDIO}`,
    `connect-src 'self' ${S3_AUDIO}${api ? ` ${api}` : ''}`,
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    'upgrade-insecure-requests',
  ].join('; ')
}

export default async function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl

  if (PROTECTED_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    const token = await getToken({ req })
    if (!token) {
      const loginUrl = new URL('/login', req.nextUrl.origin)
      loginUrl.searchParams.set('callbackUrl', `${pathname}${search}`)
      return NextResponse.redirect(loginUrl)
    }
  }

  // btoa, not Buffer: Web API only, so the middleware has no Node-runtime
  // coupling regardless of where it executes.
  const nonce = btoa(crypto.randomUUID())
  const csp = buildCsp(nonce)

  const requestHeaders = new Headers(req.headers)
  requestHeaders.set('x-nonce', nonce)
  // Next.js picks the nonce up from this request header and applies it to the
  // framework scripts it injects.
  requestHeaders.set('Content-Security-Policy', csp)

  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set('Content-Security-Policy', csp)
  return response
}

export const config = {
  // Every page (public ones included) needs the CSP; static assets and API
  // responses do not. Route group "(auth)" is not part of the URL, so the
  // protected paths above match the real paths.
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
