import { reportClientError } from '@/lib/report-client-error'

describe('reportClientError', () => {
  let fetchMock: jest.Mock

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({ ok: true })
    global.fetch = fetchMock
  })

  it('posts the message, stack and digest to the same-origin relay', () => {
    const error = Object.assign(new Error('boom'), { digest: 'abc123' })

    reportClientError(error, 'route-error')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/monitoring')
    expect(init.method).toBe('POST')
    // keepalive: the boundary often renders while the user is navigating away,
    // and a plain fetch would be cancelled with the document.
    expect(init.keepalive).toBe(true)
    expect(JSON.parse(init.body)).toMatchObject({
      message: 'boom',
      stack: error.stack,
      digest: 'abc123',
      context: 'route-error',
    })
  })

  it('sends the pathname only, never the query string', () => {
    // Query strings here carry callbackUrl and other request-shaped values; the
    // API's Sentry runs send_default_pii=False and the client must match it.
    window.history.replaceState({}, '', '/episodes/42?token=secret')

    reportClientError(new Error('boom'), 'route-error')

    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.pathname).toBe('/episodes/42')
    expect(JSON.stringify(body)).not.toContain('secret')
  })

  it('swallows a rejected relay call so the boundary still renders', async () => {
    fetchMock.mockRejectedValue(new Error('offline'))

    expect(() => reportClientError(new Error('boom'), 'route-error')).not.toThrow()
    await Promise.resolve()
  })

  it('does not throw when fetch is unavailable', () => {
    // @ts-expect-error deliberately removing fetch to model an old/locked-down runtime
    delete global.fetch

    expect(() => reportClientError(new Error('boom'), 'route-error')).not.toThrow()
  })
})
