import ApiClient from '@/lib/api-client'

// Mock EventSource globally
const MockEventSource = jest.fn().mockImplementation((url: string) => ({
  url,
  close: jest.fn(),
}))
;(global as any).EventSource = MockEventSource

function makeFetchResponse(body: any, status = 200, ok = true) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response
}

describe('ApiClient', () => {
  let client: ApiClient
  let fetchMock: jest.Mock

  beforeEach(() => {
    fetchMock = jest.fn()
    global.fetch = fetchMock
    client = new ApiClient('http://localhost:8000')
    MockEventSource.mockClear()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('setToken / getToken', () => {
    it('stores and returns the token correctly', () => {
      expect(client.getToken()).toBeNull()
      client.setToken('my-token')
      expect(client.getToken()).toBe('my-token')
    })

    it('setToken accepts null to clear the token', () => {
      client.setToken('abc')
      client.setToken(null)
      expect(client.getToken()).toBeNull()
    })
  })

  describe('get()', () => {
    it('makes a GET request with Content-Type header', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ data: 1 }))
      await client.get('/items')
      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/items',
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        })
      )
    })

    it('does NOT include Authorization header when token is null', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ data: 1 }))
      await client.get('/items')
      const headers = fetchMock.mock.calls[0][1].headers
      expect(headers['Authorization']).toBeUndefined()
    })

    it('includes Authorization: Bearer <token> when token is set', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ data: 1 }))
      client.setToken('tok123')
      await client.get('/items')
      const headers = fetchMock.mock.calls[0][1].headers
      expect(headers['Authorization']).toBe('Bearer tok123')
    })

    it('appends query params to the URL when params is passed', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ data: 1 }))
      await client.get('/items', { page: '2', limit: '10' })
      const calledUrl: string = fetchMock.mock.calls[0][0]
      expect(calledUrl).toContain('page=2')
      expect(calledUrl).toContain('limit=10')
    })
  })

  describe('post()', () => {
    it('sends data as JSON with POST method', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ id: 1 }))
      await client.post('/items', { name: 'test' })
      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/items',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'test' }),
        })
      )
    })
  })

  describe('put()', () => {
    it('uses PUT method', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ id: 1 }))
      await client.put('/items/1', { name: 'updated' })
      expect(fetchMock.mock.calls[0][1].method).toBe('PUT')
    })
  })

  describe('patch()', () => {
    it('uses PATCH method', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ id: 1 }))
      await client.patch('/items/1', { name: 'patched' })
      expect(fetchMock.mock.calls[0][1].method).toBe('PATCH')
    })
  })

  describe('delete()', () => {
    it('uses DELETE method', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({}, 200))
      await client.delete('/items/1')
      expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
    })
  })

  describe('handleResponse error handling', () => {
    it('throws the error object when response.ok is false', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ detail: 'Unauthorized' }, 401, false))
      await expect(client.get('/protected')).rejects.toMatchObject({
        detail: 'Unauthorized',
        status: 401,
      })
    })

    it('returns {} for 204 No Content responses', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        status: 204,
        json: jest.fn(),
      } as unknown as Response)
      const result = await client.delete('/items/1')
      expect(result).toEqual({})
    })
  })

  describe('createEventSource()', () => {
    it('returns an EventSource pointed at the correct URL', () => {
      const es = client.createEventSource('/events')
      expect(MockEventSource).toHaveBeenCalledWith('http://localhost:8000/events')
      expect(es).toBeDefined()
    })

    it('with includeAuth=true appends ?token=... to the URL', () => {
      client.setToken('auth-token')
      client.createEventSource('/events', true)
      expect(MockEventSource).toHaveBeenCalledWith(
        'http://localhost:8000/events?token=auth-token'
      )
    })

    it('with includeAuth=true and existing query params uses & separator', () => {
      client.setToken('auth-token')
      client.createEventSource('/events?foo=bar', true)
      expect(MockEventSource).toHaveBeenCalledWith(
        'http://localhost:8000/events?foo=bar&token=auth-token'
      )
    })

    it('does NOT append token when includeAuth=false', () => {
      client.setToken('auth-token')
      client.createEventSource('/events', false)
      const calledUrl: string = MockEventSource.mock.calls[0][0]
      expect(calledUrl).not.toContain('token=')
    })
  })

  describe('upload()', () => {
    it('uses FormData and omits Content-Type header', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ file: 'ok' }))
      const file = new File(['content'], 'test.txt', { type: 'text/plain' })
      await client.upload('/upload', file)
      const [, options] = fetchMock.mock.calls[0]
      expect(options.method).toBe('POST')
      expect(options.body).toBeInstanceOf(FormData)
      expect(options.headers['Content-Type']).toBeUndefined()
    })

    it('appends additionalData keys to FormData', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ file: 'ok' }))
      const file = new File(['content'], 'test.txt', { type: 'text/plain' })
      const appendSpy = jest.spyOn(FormData.prototype, 'append')
      await client.upload('/upload', file, { key1: 'val1', key2: 'val2' })
      expect(appendSpy).toHaveBeenCalledWith('file', file)
      expect(appendSpy).toHaveBeenCalledWith('key1', 'val1')
      expect(appendSpy).toHaveBeenCalledWith('key2', 'val2')
    })

    it('includes Authorization header when token is set', async () => {
      fetchMock.mockResolvedValue(makeFetchResponse({ file: 'ok' }))
      client.setToken('upload-token')
      const file = new File(['content'], 'test.txt', { type: 'text/plain' })
      await client.upload('/upload', file)
      const headers = fetchMock.mock.calls[0][1].headers
      expect(headers['Authorization']).toBe('Bearer upload-token')
    })
  })
})
