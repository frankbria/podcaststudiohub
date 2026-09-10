import { reportClientError } from '@/lib/report-client-error'

describe('reportClientError', () => {
  let fetchMock: jest.Mock
  const originalUrl = window.location.href

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({ ok: true })
    global.fetch = fetchMock
  })

  afterEach(() => {
    // Otherwise `?token=secret` below leaks into every later test in the file.
    window.history.replaceState({}, '', originalUrl)
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

  it('attaches a rejection handler so a failed relay never surfaces unhandled', async () => {
    // Asserted on the promise itself, not via not.toThrow(): a fire-and-forget
    // rejection escapes as an *unhandled* rejection a tick later, and whether
    // Jest fails on that is config-dependent — so not.toThrow() would pass with
    // the .catch() deleted, which is the bug this names.
    const pending = Promise.reject(new Error('offline'))
    const catchSpy = jest.spyOn(pending, 'catch')
    fetchMock.mockReturnValue(pending)

    reportClientError(new Error('boom'), 'route-error')

    expect(catchSpy).toHaveBeenCalled()
    await expect(pending).rejects.toThrow('offline')
  })

  it('truncates message and stack, which Chrome would otherwise reject wholesale', () => {
    // A keepalive fetch over 64 KiB is dropped by the browser, so the biggest
    // stacks would be the ones that never arrive.
    const error = Object.assign(new Error('x'.repeat(5000)), { stack: 'y'.repeat(50_000) })

    reportClientError(error, 'route-error')

    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.message.length).toBe(1024)
    expect(body.stack.length).toBe(8192)
    expect(fetchMock.mock.calls[0][1].body.length).toBeLessThan(64 * 1024)
  })

  it('does not throw when fetch is unavailable', () => {
    // @ts-expect-error deliberately removing fetch to model an old/locked-down runtime
    delete global.fetch

    expect(() => reportClientError(new Error('boom'), 'route-error')).not.toThrow()
  })
})
