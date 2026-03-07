import { RobustEventSource, RobustEventSourceError, ConnectionStatus } from "@/lib/event-source-client"

// --- Minimal EventSource mock ---
type EventHandler = ((event: Event | MessageEvent) => void) | null

interface MockEventSourceInstance {
  url: string
  readyState: number
  onopen: EventHandler
  onmessage: EventHandler
  onerror: EventHandler
  close: jest.Mock
  // Test helpers
  _simulateOpen: () => void
  _simulateMessage: (data: unknown) => void
  _simulateError: () => void
}

let mockInstances: MockEventSourceInstance[] = []

const MockEventSourceClass = jest.fn().mockImplementation((url: string) => {
  const instance: MockEventSourceInstance = {
    url,
    readyState: 0,
    onopen: null,
    onmessage: null,
    onerror: null,
    close: jest.fn(),
    _simulateOpen() {
      this.readyState = 1
      this.onopen?.(new Event("open"))
    },
    _simulateMessage(data: unknown) {
      const event = new MessageEvent("message", { data: JSON.stringify(data) })
      this.onmessage?.(event)
    },
    _simulateError() {
      this.readyState = 2
      this.onerror?.(new Event("error"))
    },
  }
  mockInstances.push(instance)
  return instance
})

;(global as any).EventSource = MockEventSourceClass

// Helper to get the most-recently created EventSource instance
const latestInstance = () => mockInstances[mockInstances.length - 1]

describe("RobustEventSource", () => {
  beforeEach(() => {
    jest.useFakeTimers()
    MockEventSourceClass.mockClear()
    mockInstances = []
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  // ------------------------------------------------------------------ connect
  describe("connect()", () => {
    it("creates an EventSource with the provided URL", () => {
      const onMessage = jest.fn()
      const onError = jest.fn()
      const src = new RobustEventSource("http://test/progress", { onMessage, onError })
      src.connect()
      expect(MockEventSourceClass).toHaveBeenCalledWith("http://test/progress")
      src.close()
    })

    it("calls onStatusChange with 'connecting' then 'connected'", () => {
      const statuses: ConnectionStatus[] = []
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
        onStatusChange: (s) => statuses.push(s),
      })
      src.connect()
      expect(statuses).toContain("connecting")

      latestInstance()._simulateOpen()
      expect(statuses).toContain("connected")
      src.close()
    })

    it("resets retry count on successful open", () => {
      const onError = jest.fn()
      const statuses: ConnectionStatus[] = []
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError,
        onStatusChange: (s) => statuses.push(s),
        maxRetries: 3,
        retryDelay: 100,
      })
      src.connect()

      // Trigger one error → reconnect
      latestInstance()._simulateError()
      jest.runAllTimers()

      // Open the second connection → retry count resets
      latestInstance()._simulateOpen()

      // Trigger another error – should still retry up to maxRetries
      latestInstance()._simulateError()
      jest.runAllTimers()

      // onError called for connection errors (not max_retries_exceeded)
      const connectionErrors = onError.mock.calls.filter(
        ([e]: [RobustEventSourceError]) => e.type === "connection_error"
      )
      expect(connectionErrors.length).toBe(2)
      src.close()
    })
  })

  // --------------------------------------------------- message handling
  describe("message handling", () => {
    it("calls onMessage with parsed JSON data", () => {
      const onMessage = jest.fn()
      const src = new RobustEventSource("http://test/progress", {
        onMessage,
        onError: jest.fn(),
      })
      src.connect()
      latestInstance()._simulateMessage({ status: "generating", progress: { progress: 42 } })
      expect(onMessage).toHaveBeenCalledWith({ status: "generating", progress: { progress: 42 } })
      src.close()
    })

    it("calls onError with parse_error when message JSON is invalid", () => {
      const onError = jest.fn()
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError,
      })
      src.connect()
      const instance = latestInstance()
      // Manually fire a message event with non-JSON data
      const badEvent = new MessageEvent("message", { data: "not-json{{{" })
      instance.onmessage?.(badEvent)
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ type: "parse_error" })
      )
      src.close()
    })
  })

  // --------------------------------------------------- reconnection / backoff
  describe("reconnection with exponential backoff", () => {
    it("schedules a reconnect after error with exponential delay", () => {
      const onError = jest.fn()
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError,
        maxRetries: 3,
        retryDelay: 1000,
      })
      src.connect()

      latestInstance()._simulateError()
      // After first error, delay = 1000 * 2^0 = 1000ms
      expect(MockEventSourceClass).toHaveBeenCalledTimes(1)
      jest.advanceTimersByTime(999)
      expect(MockEventSourceClass).toHaveBeenCalledTimes(1)
      jest.advanceTimersByTime(1)
      expect(MockEventSourceClass).toHaveBeenCalledTimes(2)
      src.close()
    })

    it("doubles delay on successive errors (exponential backoff)", () => {
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
        maxRetries: 5,
        retryDelay: 100,
      })
      src.connect()

      // Error 1 → delay 100ms
      latestInstance()._simulateError()
      jest.advanceTimersByTime(100)

      // Error 2 → delay 200ms
      latestInstance()._simulateError()
      jest.advanceTimersByTime(199)
      expect(MockEventSourceClass).toHaveBeenCalledTimes(2)
      jest.advanceTimersByTime(1)
      expect(MockEventSourceClass).toHaveBeenCalledTimes(3)
      src.close()
    })

    it("calls onError with connection_error and correct attempt numbers", () => {
      const onError = jest.fn()
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError,
        maxRetries: 3,
        retryDelay: 100,
      })
      src.connect()

      latestInstance()._simulateError()

      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "connection_error",
          retryAttempt: 1,
          maxRetries: 3,
        })
      )
      src.close()
    })
  })

  // --------------------------------------------------- max retries
  describe("max retries exceeded", () => {
    it("calls onError with max_retries_exceeded after all attempts fail", () => {
      const onError = jest.fn()
      const onStatusChange = jest.fn()
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError,
        onStatusChange,
        maxRetries: 3,
        retryDelay: 100,
      })
      src.connect()

      // Exhaust all retries
      for (let i = 0; i < 3; i++) {
        latestInstance()._simulateError()
        jest.runAllTimers()
      }
      // Final error on the 4th connection (retry 3)
      latestInstance()._simulateError()

      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ type: "max_retries_exceeded" })
      )
      expect(onStatusChange).toHaveBeenCalledWith("error")
    })

    it("does not create more EventSource instances after max retries", () => {
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
        maxRetries: 2,
        retryDelay: 50,
      })
      src.connect() // attempt 1

      latestInstance()._simulateError()
      jest.runAllTimers() // attempt 2

      latestInstance()._simulateError()
      jest.runAllTimers() // attempt 3

      latestInstance()._simulateError() // now max retries exceeded
      jest.runAllTimers()

      // Should have created exactly 3 instances (1 original + 2 retries)
      expect(MockEventSourceClass).toHaveBeenCalledTimes(3)
    })
  })

  // --------------------------------------------------- close
  describe("close()", () => {
    it("closes the underlying EventSource", () => {
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
      })
      src.connect()
      const instance = latestInstance()
      src.close()
      expect(instance.close).toHaveBeenCalled()
    })

    it("prevents reconnection after close()", () => {
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
        maxRetries: 3,
        retryDelay: 100,
      })
      src.connect()
      latestInstance()._simulateError()
      src.close() // close before timer fires
      jest.runAllTimers()
      // Still only the one original EventSource
      expect(MockEventSourceClass).toHaveBeenCalledTimes(1)
    })

    it("cancels pending retry timer when closed", () => {
      const clearTimeoutSpy = jest.spyOn(global, "clearTimeout")
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
        maxRetries: 3,
        retryDelay: 100,
      })
      src.connect()
      latestInstance()._simulateError()
      src.close()
      expect(clearTimeoutSpy).toHaveBeenCalled()
      clearTimeoutSpy.mockRestore()
    })
  })

  // --------------------------------------------------- no reconnect when closed
  describe("does not reconnect after close()", () => {
    it("ignores connect() call after close()", () => {
      const src = new RobustEventSource("http://test/progress", {
        onMessage: jest.fn(),
        onError: jest.fn(),
      })
      src.connect()
      src.close()
      src.connect() // should be a no-op
      // Only 1 EventSource created (the second connect is skipped)
      expect(MockEventSourceClass).toHaveBeenCalledTimes(1)
    })
  })
})
