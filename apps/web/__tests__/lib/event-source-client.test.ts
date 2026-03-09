import { RobustEventSource } from '@/lib/event-source-client'

// ---------------------------------------------------------------------------
// EventSource mock helpers
// ---------------------------------------------------------------------------

interface MockESInstance {
  url: string
  onopen: ((ev: Event) => void) | null
  onmessage: ((ev: MessageEvent) => void) | null
  onerror: ((ev: Event) => void) | null
  close: jest.Mock
  /** Helper: simulate the connection opening */
  simulateOpen: () => void
  /** Helper: simulate a message event */
  simulateMessage: (data: unknown) => void
  /** Helper: simulate an error / connection drop */
  simulateError: () => void
}

let mockInstances: MockESInstance[] = []

const MockEventSourceCtor = jest.fn().mockImplementation((url: string): MockESInstance => {
  const instance: MockESInstance = {
    url,
    onopen: null,
    onmessage: null,
    onerror: null,
    close: jest.fn(),
    simulateOpen() {
      this.onopen?.(new Event('open'))
    },
    simulateMessage(data: unknown) {
      this.onmessage?.(
        Object.assign(new Event('message'), {
          data: JSON.stringify(data),
        }) as MessageEvent
      )
    },
    simulateError() {
      this.onerror?.(new Event('error'))
    },
  }
  mockInstances.push(instance)
  return instance
})

;(global as unknown as Record<string, unknown>).EventSource = MockEventSourceCtor

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RobustEventSource', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    mockInstances = []
    MockEventSourceCtor.mockClear()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  // -------------------------------------------------------------------------
  // Happy path
  // -------------------------------------------------------------------------

  it('opens an EventSource at the provided URL', () => {
    const onMessage = jest.fn()
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', { onMessage, onError })
    res.connect()

    expect(MockEventSourceCtor).toHaveBeenCalledTimes(1)
    expect(MockEventSourceCtor).toHaveBeenCalledWith('http://test/stream')
    res.close()
  })

  it('calls onOpen callback when connection is established', () => {
    const onOpen = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError: jest.fn(),
      onOpen,
    })
    res.connect()
    mockInstances[0].simulateOpen()
    expect(onOpen).toHaveBeenCalledTimes(1)
    res.close()
  })

  it('calls onMessage with parsed JSON data', () => {
    const onMessage = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage,
      onError: jest.fn(),
    })
    res.connect()
    mockInstances[0].simulateMessage({ status: 'generating', progress: 50 })
    expect(onMessage).toHaveBeenCalledWith({ status: 'generating', progress: 50 })
    res.close()
  })

  it('resets retryCount to 0 after a successful open', () => {
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError,
      maxRetries: 3,
      retryDelay: 100,
    })
    res.connect()

    // Trigger one error → retry
    mockInstances[0].simulateError()
    expect(onError).toHaveBeenCalledTimes(1)

    jest.advanceTimersByTime(100) // retryDelay * 2^0 = 100ms
    // Second connection opens successfully
    mockInstances[1].simulateOpen()

    // Another error should reset back to attempt 1
    mockInstances[1].simulateError()
    jest.advanceTimersByTime(100)
    expect(onError).toHaveBeenCalledTimes(2)
    // retryAttempt should be 1 again (reset after open)
    expect(onError.mock.calls[1][0].retryAttempt).toBe(1)
    res.close()
  })

  // -------------------------------------------------------------------------
  // Error handling & reconnection
  // -------------------------------------------------------------------------

  it('calls onError when connection fails', () => {
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError,
      maxRetries: 3,
      retryDelay: 100,
    })
    res.connect()
    mockInstances[0].simulateError()

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toMatchObject({
      message: 'Connection lost, retrying...',
      retryAttempt: 1,
      maxRetries: 3,
    })
    res.close()
  })

  it('reconnects with exponential backoff delays', () => {
    // maxRetries=3 means 3 retry attempts → 4 connections total (1 initial + 3 retries)
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError,
      maxRetries: 3,
      retryDelay: 1000,
    })
    res.connect()

    // 1st error → retry 1 after 1000ms (1000 * 2^0)
    mockInstances[0].simulateError()
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(1)
    jest.advanceTimersByTime(999)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(1)
    jest.advanceTimersByTime(1)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(2)

    // 2nd error → retry 2 after 2000ms (1000 * 2^1)
    mockInstances[1].simulateError()
    jest.advanceTimersByTime(1999)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(2)
    jest.advanceTimersByTime(1)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(3)

    // 3rd error → retry 3 after 4000ms (1000 * 2^2)
    mockInstances[2].simulateError()
    jest.advanceTimersByTime(3999)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(3)
    jest.advanceTimersByTime(1)
    // 4th connection (3rd retry) opens
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(4)

    // 4th error → max retries reached — no more connections
    mockInstances[3].simulateError()
    jest.advanceTimersByTime(10000)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(4)
    res.close()
  })

  it('calls onMaxRetriesExceeded after exhausting all retries', () => {
    // maxRetries=2 → 2 retry attempts → 3 connections total
    // The 3rd connection's error triggers onMaxRetriesExceeded
    const onMaxRetriesExceeded = jest.fn()
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError,
      onMaxRetriesExceeded,
      maxRetries: 2,
      retryDelay: 100,
    })
    res.connect()

    // 1st error → retry 1 after 100ms
    mockInstances[0].simulateError()
    jest.advanceTimersByTime(100)
    // 2nd error → retry 2 after 200ms
    mockInstances[1].simulateError()
    jest.advanceTimersByTime(200)
    // 3rd error — retryCount(2) equals maxRetries(2) → onMaxRetriesExceeded
    mockInstances[2].simulateError()

    expect(onMaxRetriesExceeded).toHaveBeenCalledTimes(1)
    res.close()
  })

  it('does not reconnect after close() is called', () => {
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError,
      maxRetries: 3,
      retryDelay: 100,
    })
    res.connect()

    mockInstances[0].simulateError()
    // Close before retry timer fires
    res.close()
    jest.advanceTimersByTime(1000)

    // Only the original connection was opened
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(1)
  })

  it('calls close() on the EventSource instance when close() is called', () => {
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError: jest.fn(),
    })
    res.connect()
    const es = mockInstances[0]
    res.close()
    expect(es.close).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // Edge cases
  // -------------------------------------------------------------------------

  it('uses default maxRetries=5 and retryDelay=1000 when not specified', () => {
    const onError = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError,
    })
    res.connect()

    mockInstances[0].simulateError()
    expect(onError.mock.calls[0][0].maxRetries).toBe(5)

    // First retry after 1000ms
    jest.advanceTimersByTime(1000)
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(2)
    res.close()
  })

  it('ignores malformed (non-JSON) messages without throwing', () => {
    const onMessage = jest.fn()
    const res = new RobustEventSource('http://test/stream', {
      onMessage,
      onError: jest.fn(),
    })
    res.connect()
    // Simulate a non-JSON message by directly calling onmessage
    const es = mockInstances[0]
    es.onmessage?.(
      Object.assign(new Event('message'), { data: 'not-json' }) as MessageEvent
    )
    expect(onMessage).not.toHaveBeenCalled()
    res.close()
  })

  it('does nothing when connect() is called after close()', () => {
    const res = new RobustEventSource('http://test/stream', {
      onMessage: jest.fn(),
      onError: jest.fn(),
    })
    res.connect()
    res.close()
    res.connect() // should be a no-op
    expect(MockEventSourceCtor).toHaveBeenCalledTimes(1)
  })
})
