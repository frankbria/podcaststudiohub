/**
 * @jest-environment node
 *
 * Tests for the app middleware: server-side route protection (issue #222) and
 * the nonce-based Content-Security-Policy (issue #307).
 *
 * Runs in the node environment: NextRequest needs the global Request/Response
 * Web primitives, which jsdom does not provide.
 *
 * Route protection: unauthenticated requests to protected paths must redirect
 * to /login *before* any protected page renders.
 *
 * CSP: every matched page response (public and protected) must carry a
 * per-request nonce CSP whose script-src has no 'unsafe-inline'.
 */
import { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'

jest.mock('next-auth/jwt', () => ({ getToken: jest.fn() }))

process.env.NEXTAUTH_SECRET = 'test-secret'

// Imported after the mock so the middleware captures the mocked getToken.
import middleware from '@/middleware'

const mockGetToken = getToken as jest.Mock

function callMiddleware(path: string) {
  const req = new NextRequest(new URL(`http://localhost${path}`))
  return middleware(req)
}

function directive(csp: string, name: string): string {
  const match = csp.split(';').find((d) => d.trim().startsWith(`${name} `) || d.trim() === name)
  return match?.trim() ?? ''
}

afterEach(() => mockGetToken.mockReset())

describe('route protection', () => {
  it('redirects unauthenticated access to /login before render', async () => {
    mockGetToken.mockResolvedValue(null)

    const res = await callMiddleware('/dashboard')

    expect(res?.status).toBe(307)
    const location = res?.headers.get('location') ?? ''
    expect(location).toContain('/login')
    // Preserves where the user was headed so they land back after signing in.
    expect(location).toContain('callbackUrl')
  })

  it('lets authenticated requests through', async () => {
    mockGetToken.mockResolvedValue({ userId: 'u1', tenantId: 't1' })

    const res = await callMiddleware('/dashboard')

    expect(res?.status).not.toBe(307)
    expect(res?.headers.get('location') ?? '').not.toContain('/login')
  })

  it('protects /distribution (issue #316)', async () => {
    mockGetToken.mockResolvedValue(null)

    const res = await callMiddleware('/distribution')

    expect(res?.status).toBe(307)
    expect(res?.headers.get('location') ?? '').toContain('/login')
  })

  it('lets unauthenticated requests reach public pages', async () => {
    mockGetToken.mockResolvedValue(null)

    const res = await callMiddleware('/login')

    expect(res?.status).not.toBe(307)
  })
})

describe('Content-Security-Policy (issue #307)', () => {
  beforeEach(() => mockGetToken.mockResolvedValue(null))

  it('sets a CSP on public pages — including /login', async () => {
    const res = await callMiddleware('/login')
    expect(res?.headers.get('content-security-policy')).toBeTruthy()
  })

  it('sets a CSP on authenticated pages', async () => {
    mockGetToken.mockResolvedValue({ userId: 'u1' })
    const res = await callMiddleware('/dashboard')
    expect(res?.headers.get('content-security-policy')).toBeTruthy()
  })

  it('uses a nonce + strict-dynamic script-src with no unsafe-inline', async () => {
    const res = await callMiddleware('/login')
    const scriptSrc = directive(res!.headers.get('content-security-policy')!, 'script-src')

    expect(scriptSrc).toMatch(/'nonce-[A-Za-z0-9+/=]+'/)
    expect(scriptSrc).toContain("'strict-dynamic'")
    expect(scriptSrc).not.toContain("'unsafe-inline'")
  })

  it('generates a fresh nonce per request', async () => {
    const nonceOf = async () =>
      /'nonce-([^']+)'/.exec((await callMiddleware('/login'))!.headers.get('content-security-policy')!)?.[1]

    expect(await nonceOf()).not.toBe(await nonceOf())
  })

  it('forwards the nonce to the app via the x-nonce request header', async () => {
    const res = await callMiddleware('/login')
    const csp = res!.headers.get('content-security-policy')!
    const nonce = /'nonce-([^']+)'/.exec(csp)?.[1]

    // NextResponse.next({ request }) records overridden request headers here.
    const forwarded = res!.headers.get('x-middleware-request-x-nonce')
    expect(forwarded).toBe(nonce)
  })

  it('keeps unsafe-inline for styles (Radix inline style attributes)', async () => {
    const res = await callMiddleware('/login')
    const styleSrc = directive(res!.headers.get('content-security-policy')!, 'style-src')
    expect(styleSrc).toContain("'unsafe-inline'")
  })

  it('still allows S3 episode audio in media-src and connect-src', async () => {
    const res = await callMiddleware('/login')
    const csp = res!.headers.get('content-security-policy')!
    for (const src of ['media-src', 'connect-src']) {
      const value = directive(csp, src)
      expect(value).toContain('https://podcaststudiohub-audio.s3.amazonaws.com')
      expect(value).toContain('https://podcaststudiohub-audio.s3.us-east-1.amazonaws.com')
    }
  })

  it('allows the configured API origin in connect-src (signup posts to it cross-origin in dev/CI)', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8200'
    try {
      const res = await callMiddleware('/signup')
      const connectSrc = directive(res!.headers.get('content-security-policy')!, 'connect-src')
      expect(connectSrc).toContain('http://localhost:8200')
    } finally {
      delete process.env.NEXT_PUBLIC_API_URL
    }
  })

  it('ignores a same-path API URL cleanly (prod: API is same-origin behind nginx)', async () => {
    process.env.NEXT_PUBLIC_API_URL = '/api'
    try {
      const res = await callMiddleware('/signup')
      // Relative URL has no origin — CSP must stay valid with just 'self' + S3.
      const connectSrc = directive(res!.headers.get('content-security-policy')!, 'connect-src')
      expect(connectSrc).toContain("'self'")
      expect(connectSrc).not.toContain('/api')
    } finally {
      delete process.env.NEXT_PUBLIC_API_URL
    }
  })

  it('keeps the hardening directives from the old nginx policy', async () => {
    const res = await callMiddleware('/login')
    const csp = res!.headers.get('content-security-policy')!

    expect(directive(csp, 'object-src')).toContain("'none'")
    expect(directive(csp, 'frame-ancestors')).toContain("'none'")
    expect(directive(csp, 'base-uri')).toContain("'self'")
    expect(directive(csp, 'form-action')).toContain("'self'")
    expect(csp).toContain('upgrade-insecure-requests')
  })
})
