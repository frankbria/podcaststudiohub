/**
 * RobustEventSource — EventSource wrapper with exponential backoff reconnection
 * and polling fallback when SSE fails after max retries.
 */

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error"
  | "polling"
  | "complete"

export interface RobustEventSourceOptions {
  /** Called with parsed JSON data on each SSE message */
  onMessage: (data: unknown) => void
  /** Called when connection error occurs or reconnection is underway */
  onError?: (info: { message: string; attempt: number; maxRetries: number }) => void
  /** Called when all retries exhausted and polling fallback starts */
  onFallbackToPolling?: () => void
  /** Called on each status change */
  onStatusChange?: (status: ConnectionStatus) => void
  /** Maximum number of reconnection attempts (default: 5) */
  maxRetries?: number
  /** Initial delay in ms before first retry; doubles each attempt (default: 1000) */
  retryDelay?: number
}

export interface PollingOptions {
  /** URL to poll */
  url: string
  /** Fetch init options (e.g. headers) */
  fetchInit?: RequestInit
  /** Interval between polls in ms (default: 5000) */
  interval?: number
  /** Same message handler as SSE */
  onMessage: (data: unknown) => void
  /** Called if a poll request throws */
  onError?: (error: unknown) => void
  /** Return true to stop polling */
  shouldStop?: (data: unknown) => boolean
}

/**
 * Starts a polling loop as a fallback when SSE is unavailable.
 * Returns a cleanup function that stops polling.
 */
export function startPolling(options: PollingOptions): () => void {
  const {
    url,
    fetchInit,
    interval = 5000,
    onMessage,
    onError,
    shouldStop,
  } = options

  let stopped = false
  let timerId: ReturnType<typeof setTimeout> | null = null

  const poll = async () => {
    if (stopped) return
    try {
      const response = await fetch(url, fetchInit)
      if (response.ok) {
        const data = await response.json()
        onMessage(data)
        if (shouldStop?.(data)) {
          stopped = true
          return
        }
      }
    } catch (error) {
      onError?.(error)
    }
    if (!stopped) {
      timerId = setTimeout(poll, interval)
    }
  }

  // Start immediately
  poll()

  return () => {
    stopped = true
    if (timerId !== null) {
      clearTimeout(timerId)
    }
  }
}

export class RobustEventSource {
  private eventSource: EventSource | null = null
  private retryCount = 0
  private retryTimerId: ReturnType<typeof setTimeout> | null = null
  private isActive = true

  private readonly maxRetries: number
  private readonly retryDelay: number
  private readonly options: RobustEventSourceOptions

  constructor(
    private readonly url: string,
    options: RobustEventSourceOptions,
  ) {
    this.maxRetries = options.maxRetries ?? 5
    this.retryDelay = options.retryDelay ?? 1000
    this.options = options
  }

  /** Open the EventSource connection */
  connect(): void {
    if (!this.isActive) return
    this.options.onStatusChange?.("connecting")
    this._openEventSource()
  }

  private _openEventSource(): void {
    try {
      this.eventSource = new EventSource(this.url)

      this.eventSource.onopen = () => {
        this.retryCount = 0
        this.options.onStatusChange?.("connected")
      }

      this.eventSource.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)
          this.options.onMessage(data)
        } catch (err) {
          console.error("RobustEventSource: failed to parse message", err)
        }
      }

      this.eventSource.onerror = () => {
        this._handleError()
      }
    } catch (err) {
      console.error("RobustEventSource: failed to open EventSource", err)
      this._handleError()
    }
  }

  private _handleError(): void {
    this.eventSource?.close()
    this.eventSource = null

    if (!this.isActive) return

    if (this.retryCount < this.maxRetries) {
      const delay = this.retryDelay * Math.pow(2, this.retryCount)
      this.retryCount += 1

      this.options.onStatusChange?.("error")
      this.options.onError?.({
        message: "Connection lost, retrying...",
        attempt: this.retryCount,
        maxRetries: this.maxRetries,
      })

      this.retryTimerId = setTimeout(() => {
        if (!this.isActive) return
        this.options.onStatusChange?.("reconnecting")
        this._openEventSource()
      }, delay)
    } else {
      this.options.onStatusChange?.("error")
      this.options.onFallbackToPolling?.()
    }
  }

  /** Permanently close this connection and cancel any pending retries */
  close(): void {
    this.isActive = false
    if (this.retryTimerId !== null) {
      clearTimeout(this.retryTimerId)
      this.retryTimerId = null
    }
    this.eventSource?.close()
    this.eventSource = null
  }
}
