/**
 * @jest-environment node
 *
 * Tests for the same-origin API proxy Route Handler.
 *
 * The proxy reads the backend access token from the server-only NextAuth JWT
 * (httpOnly cookie, via getToken) and injects it as an Authorization header when
 * forwarding to the backend. The token must never reach the browser and must
 * never appear in a URL/query string (issue #212).
 */
import { getToken } from 'next-auth/jwt'
import { GET, POST } from '@/app/api/proxy/[...path]/route'

jest.mock('next-auth/jwt', () => ({
  getToken: jest.fn(),
}))

const getTokenMock = getToken as jest.Mock

function makeRequest(
  method: string,
  {
    path = '',
    search = '',
    headers = {},
    body,
  }: { path?: string; search?: string; headers?: Record<string, string>; body?: string } = {}
) {
  return {
    method,
    headers: new Headers(headers),
    nextUrl: { search },
    arrayBuffer: async () => (body ? new TextEncoder().encode(body).buffer : new ArrayBuffer(0)),
  } as any
}

function ctx(path: string[]) {
  return { params: Promise.resolve({ path }) }
}

describe('API proxy route handler', () => {
  let fetchMock: jest.Mock

  beforeEach(() => {
    fetchMock = jest.fn()
    global.fetch = fetchMock
    getTokenMock.mockReset()
    process.env.API_URL = 'http://backend:8000'
    process.env.NEXTAUTH_SECRET = 'test-secret'
  })

  afterEach(() => {
    jest.restoreAllMocks()
    delete process.env.API_URL
    delete process.env.NEXTAUTH_SECRET
  })

  it('returns 401 and does not call the backend when there is no access token', async () => {
    getTokenMock.mockResolvedValue(null)

    const res = await GET(makeRequest('GET', { path: 'projects' }), ctx(['projects']))

    expect(res.status).toBe(401)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('forwards GET to the backend and injects the Authorization header server-side', async () => {
    getTokenMock.mockResolvedValue({ accessToken: 'secret-jwt' })
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    )

    const res = await GET(
      makeRequest('GET', { path: 'projects', search: '?page=2' }),
      ctx(['projects'])
    )

    expect(res.status).toBe(200)
    const [calledUrl, init] = fetchMock.mock.calls[0]
    expect(calledUrl).toBe('http://backend:8000/projects?page=2')
    expect(init.method).toBe('GET')
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer secret-jwt')
  })

  it('never places the token in the request URL', async () => {
    getTokenMock.mockResolvedValue({ accessToken: 'secret-jwt' })
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))

    await GET(
      makeRequest('GET', { path: 'episodes/abc/progress', search: '' }),
      ctx(['episodes', 'abc', 'progress'])
    )

    const [calledUrl] = fetchMock.mock.calls[0]
    expect(calledUrl).not.toContain('secret-jwt')
    expect(calledUrl).not.toContain('token=')
    expect(calledUrl).toBe('http://backend:8000/episodes/abc/progress')
  })

  it('forwards the request body and content-type for POST', async () => {
    getTokenMock.mockResolvedValue({ accessToken: 'secret-jwt' })
    fetchMock.mockResolvedValue(new Response('{}', { status: 201 }))

    const res = await POST(
      makeRequest('POST', {
        path: 'projects',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name: 'x' }),
      }),
      ctx(['projects'])
    )

    expect(res.status).toBe(201)
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect((init.headers as Headers).get('content-type')).toBe('application/json')
    const forwarded = Buffer.from(init.body).toString('utf-8')
    expect(forwarded).toBe(JSON.stringify({ name: 'x' }))
  })

  it('does not forward the browser cookie header to the backend', async () => {
    getTokenMock.mockResolvedValue({ accessToken: 'secret-jwt' })
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))

    await GET(
      makeRequest('GET', { path: 'projects', headers: { cookie: 'next-auth.session-token=abc' } }),
      ctx(['projects'])
    )

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Headers).get('cookie')).toBeNull()
  })

  it('passes an SSE stream response through unchanged', async () => {
    getTokenMock.mockResolvedValue({ accessToken: 'secret-jwt' })
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"status":"complete"}\n\n'))
        controller.close()
      },
    })
    fetchMock.mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      })
    )

    const res = await GET(
      makeRequest('GET', { path: 'generation/episodes/abc/progress' }),
      ctx(['generation', 'episodes', 'abc', 'progress'])
    )

    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toBe('text/event-stream')
    const text = await res.text()
    expect(text).toContain('data: {"status":"complete"}')
  })
})
