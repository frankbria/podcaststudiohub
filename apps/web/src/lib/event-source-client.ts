/**
 * RobustEventSource – wraps EventSource with automatic exponential-backoff
 * reconnection and an optional polling fallback.
 */

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error"
  | "polling"
  | "complete"

export interface RobustEventSourceOptions {
  /** Called with parsed message data on each SSE event */
  onMessage: (data: unknown) => void
  /** Called when a connection error occurs or max retries exceeded */
  onError: (error: RobustEventSourceError) => void
  /** Called when generation finishes (status complete/failed) */
  onComplete?: () => void
  /** Called whenever the connection status changes */
  onStatusChange?: (status: ConnectionStatus) => void
  /** Maximum number of reconnection attempts before giving up (default: 5) */
  maxRetries?: number
  /** Base delay in milliseconds for exponential backoff (default: 1000) */
  retryDelay?: number
}

export interface RobustEventSourceError {
  message: string
  type: "connection_error" | "max_retries_exceeded" | "parse_error"
  retryAttempt?: number
  maxRetries?: number
}

export class RobustEventSource {
  private eventSource: EventSource | null = null
  private retryCount = 0
  private readonly maxRetries: number
  private readonly retryDelay: number
  private isActive = true
  private retryTimer: ReturnType<typeof setTimeout> | null = null

  constructor(
    private readonly url: string,
    private readonly options: RobustEventSourceOptions
  ) {
    this.maxRetries = options.maxRetries ?? 5
    this.retryDelay = options.retryDelay ?? 1000
  }

  connect(): void {
    if (!this.isActive) return

    this.options.onStatusChange?.("connecting")

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
        } catch {
          this.options.onError({
            message: "Failed to parse SSE message",
            type: "parse_error",
          })
        }
      }

      this.eventSource.onerror = () => {
        this.eventSource?.close()
        this.eventSource = null
        this.scheduleReconnect()
      }
    } catch {
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect(): void {
    if (!this.isActive) return

    if (this.retryCount < this.maxRetries) {
      const delay = this.retryDelay * Math.pow(2, this.retryCount)
      this.retryCount++

      this.options.onError({
        message: "Connection lost, retrying...",
        type: "connection_error",
        retryAttempt: this.retryCount,
        maxRetries: this.maxRetries,
      })
      this.options.onStatusChange?.("reconnecting")

      this.retryTimer = setTimeout(() => {
        if (this.isActive) {
          this.connect()
        }
      }, delay)
    } else {
      this.options.onError({
        message: "Failed to connect after multiple attempts",
        type: "max_retries_exceeded",
        retryAttempt: this.retryCount,
        maxRetries: this.maxRetries,
      })
      this.options.onStatusChange?.("error")
    }
  }

  close(): void {
    this.isActive = false
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.eventSource?.close()
    this.eventSource = null
  }
}
