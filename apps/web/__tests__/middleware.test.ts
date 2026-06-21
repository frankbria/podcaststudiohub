/**
 * @jest-environment node
 *
 * Tests for server-side route protection (issue #222).
 *
 * Runs in the node environment: NextRequest needs the global Request/Response
 * Web primitives, which jsdom does not provide.
 *
 * The middleware must redirect unauthenticated requests to /login *before* any
 * protected page renders, instead of relying solely on the client-side redirect.
 */
import { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'

jest.mock('next-auth/jwt', () => ({ getToken: jest.fn() }))

// withAuth reads the secret from the environment at call time.
process.env.NEXTAUTH_SECRET = 'test-secret'

// Imported after the mock so withAuth captures the mocked getToken.
import middleware from '@/middleware'

const mockGetToken = getToken as jest.Mock

function callMiddleware(path: string) {
  const req = new NextRequest(new URL(`http://localhost${path}`))
  // withAuth ignores the NextFetchEvent for redirect decisions.
  return middleware(req as never, {} as never)
}

afterEach(() => mockGetToken.mockReset())

describe('route protection middleware', () => {
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

    // withAuth returns undefined (or a pass-through NextResponse.next()) when the
    // session is valid — never a redirect to /login.
    expect(res?.status).not.toBe(307)
    expect(res?.headers.get('location') ?? '').not.toContain('/login')
  })
})
