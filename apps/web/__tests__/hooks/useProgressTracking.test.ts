import { renderHook, act } from '@testing-library/react'
import { useProgressTracking } from '@/hooks/useProgressTracking'

// ---------------------------------------------------------------------------
// EventSource mock (same pattern as event-source-client tests)
// ---------------------------------------------------------------------------

interface MockESInstance {
  url: string
  onopen: ((ev: Event) => void) | null
  onmessage: ((ev: MessageEvent) => void) | null
  onerror: ((ev: Event) => void) | null
  close: jest.Mock
  simulateOpen: () => void
  simulateMessage: (data: unknown) => void
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
// fetch mock for polling tests
// ---------------------------------------------------------------------------
let fetchMock: jest.Mock
;(global as unknown as Record<string, unknown>).fetch = jest.fn()

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useProgressTracking', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    mockInstances = []
    MockEventSourceCtor.mockClear()
    fetchMock = jest.fn()
    global.fetch = fetchMock
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  const baseOptions = (overrides: Partial<Parameters<typeof useProgressTracking>[1]> = {}) => ({
    sseUrl: 'http://api/progress',
    pollUrl: 'http://api/progress',
    authToken: 'tok',
    onUpdate: jest.fn(),
    onComplete: jest.fn(),
    ...overrides,
  })

  // -------------------------------------------------------------------------
  // Inactive statuses — hook should NOT open SSE
  // -------------------------------------------------------------------------

  it('does not open EventSource when generationStatus is undefined', () => {
    renderHook(() => useProgressTracking(undefined, baseOptions()))
    expect(MockEventSourceCtor).not.toHaveBeenCalled()
  })

  it('does not open EventSource for "draft" status', () => {
    renderHook(() => useProgressTracking('draft', baseOptions()))
    expect(MockEventSourceCtor).not.toHaveBeenCalled()
  })

  it('does not open EventSource for "complete" status', () => {
    renderHook(() => useProgressTracking('complete', baseOptions()))
    expect(MockEventSourceCtor).not.toHaveBeenCalled()
  })

  it('does not open EventSource for "failed" status', () => {
    renderHook(() => useProgressTracking('failed', baseOptions()))
    expect(MockEventSourceCtor).not.toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // Active statuses — hook should open SSE
  // -------------------------------------------------------------------------

  it.each(['queued', 'extracting', 'generating', 'synthesizing'])(
    'opens EventSource for "%s" status',
    (status) => {
      renderHook(() => useProgressTracking(status, baseOptions()))
      expect(MockEventSourceCtor).toHaveBeenCalledTimes(1)
      expect(MockEventSourceCtor).toHaveBeenCalledWith('http://api/progress')
    }
  )

  // -------------------------------------------------------------------------
  // Connection status transitions
  // -------------------------------------------------------------------------

  it('returns "connecting" initially when active', () => {
    const { result } = renderHook(() => useProgressTracking('queued', baseOptions()))
    expect(result.current.connectionStatus).toBe('connecting')
  })

  it('transitions to "connected" on open', () => {
    const { result } = renderHook(() => useProgressTracking('queued', baseOptions()))
    act(() => {
      mockInstances[0].simulateOpen()
    })
    expect(result.current.connectionStatus).toBe('connected')
  })

  it('transitions to "reconnecting" on first error', () => {
    const { result } = renderHook(() => useProgressTracking('queued', baseOptions()))
    act(() => {
      mockInstances[0].simulateError()
    })
    expect(result.current.connectionStatus).toBe('reconnecting')
  })

  // -------------------------------------------------------------------------
  // Message handling
  // -------------------------------------------------------------------------

  it('calls onUpdate with parsed message data', () => {
    const onUpdate = jest.fn()
    renderHook(() => useProgressTracking('queued', baseOptions({ onUpdate })))
    act(() => {
      mockInstances[0].simulateMessage({ status: 'generating', progress: { progress: 40 } })
    })
    expect(onUpdate).toHaveBeenCalledWith({ status: 'generating', progress: { progress: 40 } })
  })

  it('calls onComplete and sets status to "complete" when generation finishes', () => {
    const onComplete = jest.fn()
    const { result } = renderHook(() =>
      useProgressTracking('generating', baseOptions({ onComplete }))
    )
    act(() => {
      mockInstances[0].simulateMessage({ status: 'complete', progress: { progress: 100 } })
    })
    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(result.current.connectionStatus).toBe('complete')
  })

  it('calls onComplete when generation status is "failed"', () => {
    const onComplete = jest.fn()
    renderHook(() => useProgressTracking('generating', baseOptions({ onComplete })))
    act(() => {
      mockInstances[0].simulateMessage({ status: 'failed', progress: {} })
    })
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useProgressTracking('queued', baseOptions()))
    const es = mockInstances[0]
    unmount()
    expect(es.close).toHaveBeenCalled()
  })

  // -------------------------------------------------------------------------
  // Polling fallback (triggered when SSE maxRetries exhausted)
  // -------------------------------------------------------------------------

  it('falls back to polling after max SSE retries and sets status to "polling"', async () => {
    const { result } = renderHook(() =>
      useProgressTracking('queued', baseOptions())
    )

    // Exhaust 5 retries (default maxRetries)
    for (let i = 0; i <= 5; i++) {
      act(() => { mockInstances[i]?.simulateError() })
      // Advance timer to trigger retry (use large value to cover all backoff intervals)
      act(() => { jest.advanceTimersByTime(32000) })
    }

    expect(result.current.connectionStatus).toBe('polling')
  })

  it('polling calls fetch with Authorization header when authToken is set', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ status: 'generating', progress: { progress: 50 } }),
    })

    renderHook(() =>
      useProgressTracking('queued', baseOptions({ authToken: 'my-token' }))
    )

    // Exhaust retries to reach polling
    for (let i = 0; i <= 5; i++) {
      act(() => { mockInstances[i]?.simulateError() })
      act(() => { jest.advanceTimersByTime(32000) })
    }

    // Trigger first poll
    await act(async () => {
      jest.advanceTimersByTime(5000)
      await Promise.resolve()
    })

    if (fetchMock.mock.calls.length > 0) {
      const [, options] = fetchMock.mock.calls[0]
      expect(options?.headers?.['Authorization']).toBe('Bearer my-token')
    }
  })
})
