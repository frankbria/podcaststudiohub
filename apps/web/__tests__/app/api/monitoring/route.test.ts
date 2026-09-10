/**
 * @jest-environment node
 *
 * Tests for the client-error relay Route Handler (issue #485, item 3).
 *
 * The browser has no Sentry DSN: `error.tsx` / `global-error.tsx` POST here
 * same-origin, and this handler forwards a Sentry envelope using the SAME
 * server-side `SENTRY_DSN` the API and Celery worker read. That keeps the DSN
 * out of the client bundle and keeps the strict-dynamic CSP unchanged
 * (`connect-src 'self'` already covers a same-origin POST).
 *
 * The gate copies `init_sentry()` in apps/api: no DSN -> hard no-op, so local
 * dev and CI never phone home.
 */
import { POST } from '@/app/api/monitoring/route'

const DSN = 'https://abc123@o42.ingest.sentry.io/4507'

function makeRequest(
  body: unknown,
  {
    raw,
    contentLength,
    fetchSite,
  }: { raw?: string; contentLength?: string; fetchSite?: string } = {}
) {
  const text = raw ?? JSON.stringify(body)
  const headers = new Headers()
  if (contentLength !== undefined) headers.set('content-length', contentLength)
  if (fetchSite !== undefined) headers.set('sec-fetch-site', fetchSite)
  return {
    headers,
    text: async () => text,
  } as unknown as Request
}

describe('POST /api/monitoring', () => {
  let fetchMock: jest.Mock

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({ ok: true })
    global.fetch = fetchMock
    process.env.SENTRY_DSN = DSN
    delete process.env.SENTRY_ENVIRONMENT
  })

  afterEach(() => {
    delete process.env.SENTRY_DSN
    delete process.env.SENTRY_ENVIRONMENT
    jest.restoreAllMocks()
  })

  /** Pull the three envelope lines out of the captured fetch body. */
  function sentEnvelope() {
    const [, init] = fetchMock.mock.calls[0]
    const [header, itemHeader, payload] = (init.body as string).trim().split('\n')
    return {
      url: fetchMock.mock.calls[0][0] as string,
      header: JSON.parse(header),
      itemHeader: JSON.parse(itemHeader),
      event: JSON.parse(payload),
    }
  }

  it('no-ops with 204 and sends nothing when SENTRY_DSN is unset', async () => {
    delete process.env.SENTRY_DSN

    const response = await POST(makeRequest({ message: 'boom' }))

    expect(response.status).toBe(204)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('no-ops with 204 when SENTRY_DSN is not a parseable DSN', async () => {
    process.env.SENTRY_DSN = 'not-a-dsn'

    const response = await POST(makeRequest({ message: 'boom' }))

    expect(response.status).toBe(204)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('posts an envelope to the DSN-derived ingest URL', async () => {
    const response = await POST(makeRequest({ message: 'boom' }))

    expect(response.status).toBe(202)
    const { url, itemHeader } = sentEnvelope()
    expect(url).toBe(
      'https://o42.ingest.sentry.io/api/4507/envelope/?sentry_key=abc123&sentry_version=7'
    )
    expect(itemHeader).toEqual({ type: 'event' })
  })

  it('tags the event with the digest so error.tsx references are searchable', async () => {
    await POST(makeRequest({ message: 'boom', digest: 'abc123def', context: 'global-error' }))

    const { event, header } = sentEnvelope()
    expect(event.tags).toMatchObject({ digest: 'abc123def', context: 'global-error' })
    // The envelope header event_id must match the event's, or Sentry drops it.
    expect(header.event_id).toBe(event.event_id)
    expect(event.event_id).toMatch(/^[0-9a-f]{32}$/)
  })

  it('omits the digest tag when the error had none', async () => {
    await POST(makeRequest({ message: 'boom' }))

    expect(sentEnvelope().event.tags.digest).toBeUndefined()
  })

  it('sends the message as the exception value so Sentry groups by it', async () => {
    await POST(makeRequest({ message: 'Minified React error #31', stack: 'at x\nat y' }))

    const { event } = sentEnvelope()
    expect(event.exception.values[0]).toMatchObject({
      type: 'Error',
      value: 'Minified React error #31',
    })
    expect(event.extra.stack).toBe('at x\nat y')
    expect(event.platform).toBe('javascript')
    expect(event.level).toBe('error')
  })

  it('reports the environment so client events filter alongside the API events', async () => {
    process.env.SENTRY_ENVIRONMENT = 'staging'

    await POST(makeRequest({ message: 'boom' }))

    expect(sentEnvelope().event.environment).toBe('staging')
  })

  it('truncates oversized fields rather than relaying them', async () => {
    await POST(makeRequest({ message: 'x'.repeat(5000), stack: 'y'.repeat(20000) }))

    const { event } = sentEnvelope()
    expect(event.exception.values[0].value.length).toBeLessThanOrEqual(1024)
    expect(event.extra.stack.length).toBeLessThanOrEqual(8192)
  })

  it('rejects an oversized Content-Length before reading the body', async () => {
    // The cap has to bite before request.text() buffers, or an unauthenticated
    // caller chooses the allocation size.
    const text = jest.fn()
    const response = await POST({
      headers: new Headers({ 'content-length': String(10 * 1024 * 1024) }),
      text,
    } as unknown as Request)

    expect(response.status).toBe(413)
    expect(text).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects an oversized body that declared no Content-Length', async () => {
    const response = await POST(makeRequest(null, { raw: 'z'.repeat(70_000) }))

    expect(response.status).toBe(413)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects a non-JSON body without calling Sentry', async () => {
    const response = await POST(makeRequest(null, { raw: '<html>' }))

    expect(response.status).toBe(400)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects a body with no usable message', async () => {
    const response = await POST(makeRequest({ digest: 'abc' }))

    expect(response.status).toBe(400)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('coerces non-string fields instead of relaying attacker-shaped values', async () => {
    await POST(makeRequest({ message: 'boom', digest: { evil: true }, context: 42 }))

    const { event } = sentEnvelope()
    expect(event.tags.digest).toBeUndefined()
    expect(event.tags.context).toBeUndefined()
  })

  it('still answers 202 when the Sentry ingest call fails', async () => {
    fetchMock.mockRejectedValue(new Error('ingest down'))
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})

    const response = await POST(makeRequest({ message: 'boom' }))

    expect(response.status).toBe(202)
    expect(consoleError).toHaveBeenCalled()
  })

  it('logs a non-2xx from Sentry instead of reporting success', async () => {
    // A typo'd DSN is a 401 and an exhausted quota is a 429; both resolve
    // normally, so without this the relay looks healthy while relaying nothing.
    fetchMock.mockResolvedValue({ ok: false, status: 401 })
    const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {})

    await POST(makeRequest({ message: 'boom' }))

    expect(consoleError).toHaveBeenCalledWith(
      expect.stringContaining('401')
    )
  })

  it('rejects a cross-site POST, which CORS would not stop', async () => {
    // A cross-site <form enctype="text/plain"> can post a body that parses as
    // JSON with no preflight — free quota burn from any page a user visits.
    const response = await POST(makeRequest({ message: 'boom' }, { fetchSite: 'cross-site' }))

    expect(response.status).toBe(403)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('accepts a same-origin POST', async () => {
    const response = await POST(makeRequest({ message: 'boom' }, { fetchSite: 'same-origin' }))

    expect(response.status).toBe(202)
    expect(fetchMock).toHaveBeenCalled()
  })

  it('accepts a client that sends no Sec-Fetch-Site at all', async () => {
    // curl and pre-2023 Safari omit it; they are not the browser vector above,
    // and rejecting them would drop real reports.
    const response = await POST(makeRequest({ message: 'boom' }))

    expect(response.status).toBe(202)
  })

  it('fingerprints by digest so redacted production errors do not collapse', async () => {
    // A production Server Component throw reaches the boundary with its message
    // replaced by Next's generic string, so message-only grouping would fold
    // every such crash into a single Sentry issue.
    await POST(makeRequest({ message: 'An error occurred', digest: 'digest-a' }))
    await POST(makeRequest({ message: 'An error occurred', digest: 'digest-b' }))

    const fingerprints = fetchMock.mock.calls.map(
      ([, init]) => JSON.parse((init.body as string).trim().split('\n')[2]).fingerprint
    )
    expect(fingerprints[0]).toEqual(['{{ default }}', 'digest-a'])
    expect(fingerprints[1]).toEqual(['{{ default }}', 'digest-b'])
  })

  it('omits the fingerprint when there is no digest to split on', async () => {
    await POST(makeRequest({ message: 'boom' }))

    expect(sentEnvelope().event.fingerprint).toBeUndefined()
  })

  it('sends an ISO 8601 timestamp matching the envelope header', async () => {
    await POST(makeRequest({ message: 'boom' }))

    const { event, header } = sentEnvelope()
    expect(event.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/)
    expect(event.timestamp).toBe(header.sent_at)
  })

  it('percent-encodes a DSN key that would otherwise corrupt the query string', async () => {
    process.env.SENTRY_DSN = 'https://a+b%26c@o42.ingest.sentry.io/4507'

    await POST(makeRequest({ message: 'boom' }))

    expect(sentEnvelope().url).toContain('sentry_key=a%2Bb%26c&')
  })
})
