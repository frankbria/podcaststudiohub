import {
  RobustEventSource,
  startPolling,
  ConnectionStatus,
} from "@/lib/event-source-manager"

// ---------------------------------------------------------------------------
// Minimal EventSource mock
// ---------------------------------------------------------------------------

interface MockESInstance {
  url: string
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onerror: ((event: Event) => void) | null
  close: jest.Mock
  readyState: number
  // helpers for tests
  _triggerOpen: () => void
  _triggerMessage: (data: unknown) => void
  _triggerError: () => void
}

let mockESInstances: MockESInstance[] = []

const MockEventSource = jest.fn().mockImplementation((url: string): MockESInstance => {
  const instance: MockESInstance = {
    url,
    onopen: null,
    onmessage: null,
    onerror: null,
    close: jest.fn(),
    readyState: 0, // CONNECTING
    _triggerOpen() {
      this.readyState = 1 // OPEN
      this.onopen?.(new Event("open"))
    },
    _triggerMessage(data: unknown) {
      const event = { data: JSON.stringify(data) } as MessageEvent
      this.onmessage?.(event)
    },
    _triggerError() {
      this.readyState = 2 // CLOSED
      this.onerror?.(new Event("error"))
    },
  }
  mockESInstances.push(instance)
  return instance
})

;(global as any).EventSource = MockEventSource

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRobust(overrides: Partial<ConstructorParameters<typeof RobustEventSource>[1]> = {}) {
  const onMessage = jest.fn()
  const onError = jest.fn()
  const onFallbackToPolling = jest.fn()
  const onStatusChange = jest.fn()

  const es = new RobustEventSource("http://localhost/sse", {
    onMessage,
    onError,
    onFallbackToPolling,
    onStatusChange,
    maxRetries: 3,
    retryDelay: 100, // short for tests
    ...overrides,
  })

  return { es, onMessage, onError, onFallbackToPolling, onStatusChange }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  jest.useFakeTimers()
  mockESInstances = []
  MockEventSource.mockClear()
})

afterEach(() => {
  jest.useRealTimers()
})

// ---------------------------------------------------------------------------
// RobustEventSource — happy path
// ---------------------------------------------------------------------------

describe("RobustEventSource — happy path", () => {
  it("creates EventSource at the correct URL on connect()", () => {
    const { es } = makeRobust()
    es.connect()
    expect(MockEventSource).toHaveBeenCalledTimes(1)
    expect(MockEventSource).toHaveBeenCalledWith("http://localhost/sse")
  })

  it("emits 'connecting' then 'connected' on successful open", () => {
    const { es, onStatusChange } = makeRobust()
    es.connect()
    expect(onStatusChange).toHaveBeenCalledWith("connecting")

    mockESInstances[0]._triggerOpen()
    expect(onStatusChange).toHaveBeenCalledWith("connected")
  })

  it("calls onMessage with parsed data on SSE message", () => {
    const { es, onMessage } = makeRobust()
    es.connect()
    mockESInstances[0]._triggerMessage({ status: "generating", progress: { progress: 42 } })
    expect(onMessage).toHaveBeenCalledWith({ status: "generating", progress: { progress: 42 } })
  })

  it("resets retryCount to 0 on successful open", () => {
    const { es, onFallbackToPolling } = makeRobust()
    es.connect()

    // Trigger one error (retryCount → 1)
    mockESInstances[0]._triggerError()
    jest.advanceTimersByTime(100)

    // New connection opens successfully → retryCount reset to 0
    mockESInstances[1]._triggerOpen()

    // Trigger maxRetries+1 errors to exhaust the fresh retry budget (maxRetries=3)
    // ES[1] error: retryCount 0→1, delay 100ms
    // ES[2] error: retryCount 1→2, delay 200ms
    // ES[3] error: retryCount 2→3, delay 400ms
    // ES[4] error: retryCount 3 >= maxRetries(3) → fallback
    for (let i = 1; i <= 4; i++) {
      mockESInstances[i]._triggerError()
      jest.advanceTimersByTime(100 * Math.pow(2, i))
    }

    // Because retryCount was reset after the successful open, all 3 configured
    // retries are used up and fallback fires.
    expect(onFallbackToPolling).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// RobustEventSource — error handling & reconnection
// ---------------------------------------------------------------------------

describe("RobustEventSource — error handling & reconnection", () => {
  it("emits 'error' status on connection failure", () => {
    const { es, onStatusChange } = makeRobust()
    es.connect()
    mockESInstances[0]._triggerError()
    expect(onStatusChange).toHaveBeenCalledWith("error")
  })

  it("calls onError with attempt info on each failure", () => {
    const { es, onError } = makeRobust()
    es.connect()
    mockESInstances[0]._triggerError()
    expect(onError).toHaveBeenCalledWith({
      message: "Connection lost, retrying...",
      attempt: 1,
      maxRetries: 3,
    })
  })

  it("schedules reconnect with exponential backoff (1× → 2× → 4× base delay)", () => {
    const { es } = makeRobust()
    es.connect()

    // First error → delay = 100ms
    mockESInstances[0]._triggerError()
    expect(MockEventSource).toHaveBeenCalledTimes(1)
    jest.advanceTimersByTime(99)
    expect(MockEventSource).toHaveBeenCalledTimes(1) // not yet
    jest.advanceTimersByTime(1)
    expect(MockEventSource).toHaveBeenCalledTimes(2) // reconnected

    // Second error → delay = 200ms
    mockESInstances[1]._triggerError()
    jest.advanceTimersByTime(199)
    expect(MockEventSource).toHaveBeenCalledTimes(2)
    jest.advanceTimersByTime(1)
    expect(MockEventSource).toHaveBeenCalledTimes(3)

    // Third error → delay = 400ms
    mockESInstances[2]._triggerError()
    jest.advanceTimersByTime(399)
    expect(MockEventSource).toHaveBeenCalledTimes(3)
    jest.advanceTimersByTime(1)
    expect(MockEventSource).toHaveBeenCalledTimes(4)
  })

  it("emits 'reconnecting' status when the retry timer fires", () => {
    const { es, onStatusChange } = makeRobust()
    es.connect()
    mockESInstances[0]._triggerError()

    // Before the timer fires we should see 'error'
    expect(onStatusChange).toHaveBeenCalledWith("error")

    jest.advanceTimersByTime(100)
    expect(onStatusChange).toHaveBeenCalledWith("reconnecting")
  })

  it("calls onFallbackToPolling after maxRetries exhausted", () => {
    const { es, onFallbackToPolling } = makeRobust()
    es.connect()

    for (let i = 0; i < 3; i++) {
      mockESInstances[i]._triggerError()
      jest.advanceTimersByTime(100 * Math.pow(2, i))
    }

    // 4th error exhausts maxRetries=3
    mockESInstances[3]._triggerError()
    expect(onFallbackToPolling).toHaveBeenCalledTimes(1)
  })

  it("does NOT create more EventSource instances after maxRetries", () => {
    const { es } = makeRobust()
    es.connect()

    for (let i = 0; i < 3; i++) {
      mockESInstances[i]._triggerError()
      jest.advanceTimersByTime(100 * Math.pow(2, i))
    }

    // Exhaust
    mockESInstances[3]._triggerError()

    // Advance more time — no further reconnect attempts
    jest.advanceTimersByTime(10000)
    expect(MockEventSource).toHaveBeenCalledTimes(4) // original + 3 retries
  })
})

// ---------------------------------------------------------------------------
// RobustEventSource — cleanup
// ---------------------------------------------------------------------------

describe("RobustEventSource — cleanup", () => {
  it("closes the underlying EventSource on close()", () => {
    const { es } = makeRobust()
    es.connect()
    const instance = mockESInstances[0]
    es.close()
    expect(instance.close).toHaveBeenCalled()
  })

  it("cancels pending retry timer on close()", () => {
    const { es } = makeRobust()
    es.connect()
    mockESInstances[0]._triggerError() // schedules retry in 100ms

    es.close() // should cancel the timer

    jest.advanceTimersByTime(200)
    // No new EventSource should have been created
    expect(MockEventSource).toHaveBeenCalledTimes(1)
  })

  it("does not reconnect after close() is called", () => {
    const { es } = makeRobust()
    es.connect()
    es.close()

    jest.advanceTimersByTime(10000)
    expect(MockEventSource).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// RobustEventSource — message parse error is swallowed
// ---------------------------------------------------------------------------

describe("RobustEventSource — malformed messages", () => {
  it("does not throw when SSE data is not valid JSON", () => {
    const { es, onMessage } = makeRobust()
    es.connect()

    const instance = mockESInstances[0]
    // Manually trigger with raw invalid JSON (bypass _triggerMessage helper)
    instance.onmessage?.({ data: "{not-json}" } as MessageEvent)

    expect(onMessage).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// startPolling
// ---------------------------------------------------------------------------

describe("startPolling", () => {
  let fetchMock: jest.Mock

  beforeEach(() => {
    fetchMock = jest.fn()
    global.fetch = fetchMock
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it("calls fetch immediately on start", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: jest.fn().mockResolvedValue({ status: "generating" }) })
    const onMessage = jest.fn()

    const stop = startPolling({
      url: "http://localhost/poll",
      onMessage,
      interval: 5000,
    })

    await Promise.resolve() // flush microtask
    await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    stop()
  })

  it("calls onMessage with parsed response data", async () => {
    const responseData = { status: "complete", progress: { progress: 100 } }
    fetchMock.mockResolvedValue({ ok: true, json: jest.fn().mockResolvedValue(responseData) })
    const onMessage = jest.fn()

    const stop = startPolling({ url: "http://localhost/poll", onMessage, interval: 5000 })

    await Promise.resolve()
    await Promise.resolve()
    expect(onMessage).toHaveBeenCalledWith(responseData)
    stop()
  })

  it("stops polling when shouldStop returns true", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: jest.fn().mockResolvedValue({ status: "complete" }) })
    const onMessage = jest.fn()

    const stop = startPolling({
      url: "http://localhost/poll",
      onMessage,
      interval: 1000,
      shouldStop: (data: any) => data.status === "complete",
    })

    await Promise.resolve()
    await Promise.resolve()

    jest.advanceTimersByTime(5000)
    // Even after advancing time, no additional polls after shouldStop=true
    expect(fetchMock).toHaveBeenCalledTimes(1)
    stop()
  })

  it("calls onError when fetch throws", async () => {
    const networkError = new Error("network error")
    fetchMock.mockRejectedValue(networkError)
    const onMessage = jest.fn()
    const onError = jest.fn()

    const stop = startPolling({ url: "http://localhost/poll", onMessage, onError, interval: 5000 })

    await Promise.resolve()
    await Promise.resolve()
    expect(onError).toHaveBeenCalledWith(networkError)
    stop()
  })

  it("cleanup function stops subsequent polls", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: jest.fn().mockResolvedValue({ status: "generating" }) })
    const onMessage = jest.fn()

    const stop = startPolling({ url: "http://localhost/poll", onMessage, interval: 1000 })
    await Promise.resolve()
    await Promise.resolve()

    stop()
    jest.advanceTimersByTime(5000)

    // Only the initial immediate poll should have fired
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
