import { authenticateCredentials } from '@/lib/auth'

function makeFetchResponse(body: any, ok = true, status = 200) {
  return {
    ok,
    status,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response
}

describe('authenticateCredentials', () => {
  let fetchMock: jest.Mock

  beforeEach(() => {
    fetchMock = jest.fn()
    global.fetch = fetchMock
    process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000'
  })

  afterEach(() => {
    jest.restoreAllMocks()
    delete process.env.NEXT_PUBLIC_API_URL
  })

  it('returns null when email is missing', async () => {
    const result = await authenticateCredentials(undefined, 'password')
    expect(result).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('returns null when password is missing', async () => {
    const result = await authenticateCredentials('user@example.com', undefined)
    expect(result).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('returns null when both email and password are missing', async () => {
    const result = await authenticateCredentials(undefined, undefined)
    expect(result).toBeNull()
  })

  it('returns null when the backend responds with a non-OK status', async () => {
    fetchMock.mockResolvedValue(makeFetchResponse({ detail: 'Invalid credentials' }, false, 401))
    const result = await authenticateCredentials('user@example.com', 'wrong')
    expect(result).toBeNull()
  })

  it('returns null when fetch throws', async () => {
    fetchMock.mockRejectedValue(new Error('Network error'))
    const result = await authenticateCredentials('user@example.com', 'password')
    expect(result).toBeNull()
  })

  it('returns the correct user object on success', async () => {
    const backendResponse = {
      access_token: 'tok-abc',
      user: {
        id: 'user-1',
        email: 'user@example.com',
        full_name: 'Test User',
        tenant_id: 'tenant-42',
      },
    }
    fetchMock.mockResolvedValue(makeFetchResponse(backendResponse, true, 200))

    const result = await authenticateCredentials('user@example.com', 'pass123')
    expect(result).toEqual({
      id: 'user-1',
      email: 'user@example.com',
      name: 'Test User',
      accessToken: 'tok-abc',
      tenantId: 'tenant-42',
    })
  })

  it('calls the correct endpoint with POST and JSON body', async () => {
    const backendResponse = {
      access_token: 'tok-abc',
      user: { id: '1', email: 'a@b.com', full_name: 'A B', tenant_id: 't1' },
    }
    fetchMock.mockResolvedValue(makeFetchResponse(backendResponse))

    await authenticateCredentials('a@b.com', 'secret')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/auth/login',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'a@b.com', password: 'secret' }),
      })
    )
  })
})

describe('authOptions callbacks', () => {
  it('jwt callback sets accessToken, tenantId, userId on initial sign in', async () => {
    const { authOptions } = require('@/lib/auth')
    const jwtCallback = authOptions.callbacks.jwt
    const token = {}
    const user = { id: 'u1', accessToken: 'tok', tenantId: 'ten1' }
    const result = await jwtCallback({ token, user })
    expect(result).toMatchObject({
      accessToken: 'tok',
      tenantId: 'ten1',
      userId: 'u1',
    })
  })

  it('jwt callback does not modify token when user is absent', async () => {
    const { authOptions } = require('@/lib/auth')
    const jwtCallback = authOptions.callbacks.jwt
    const token = { existing: 'val' }
    const result = await jwtCallback({ token, user: undefined })
    expect(result).toEqual({ existing: 'val' })
  })

  it('session callback maps token properties to session', async () => {
    const { authOptions } = require('@/lib/auth')
    const sessionCallback = authOptions.callbacks.session
    const token = { userId: 'u1', tenantId: 'ten1', accessToken: 'tok' }
    const session = { user: {}, expires: '' }
    const result = await sessionCallback({ session, token })
    expect(result.user.id).toBe('u1')
    expect((result.user as any).tenantId).toBe('ten1')
    expect((result as any).accessToken).toBe('tok')
  })
})
