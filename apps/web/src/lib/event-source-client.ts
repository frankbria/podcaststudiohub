/**
 * Robust EventSource wrapper with automatic reconnection and exponential backoff.
 *
 * The native EventSource API has no built-in retry limits or error reporting.
 * This class adds:
 *  - onerror handler that captures connection failures
 *  - Exponential backoff reconnection (1s → 2s → 4s … up to maxRetries)
 *  - Configurable maximum retry count
 *  - Lifecycle callbacks: onOpen, onMessage, onError, onMaxRetriesExceeded
 *  - Clean shutdown via close()
 */

export type ConnectionStatus =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'
  | 'polling'
  | 'complete'

export interface RobustEventSourceOptions {
  /** Called when a message is received (already JSON-parsed). */
  onMessage: (data: unknown) => void
  /** Called on each connection error or retry attempt. */
  onError: (info: { message: string; retryAttempt: number; maxRetries: number }) => void
  /** Called when all retry attempts are exhausted. */
  onMaxRetriesExceeded?: () => void
  /** Called when the connection opens successfully. */
  onOpen?: () => void
  /** Maximum number of reconnection attempts (default: 5). */
  maxRetries?: number
  /** Initial delay in milliseconds before first retry (default: 1000). */
  retryDelay?: number
}

export class RobustEventSource {
  private eventSource: EventSource | null = null
  private retryCount = 0
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private isActive = true

  private readonly maxRetries: number
  private readonly retryDelay: number

  constructor(
    private readonly url: string,
    private readonly options: RobustEventSourceOptions
  ) {
    this.maxRetries = options.maxRetries ?? 5
    this.retryDelay = options.retryDelay ?? 1000
  }

  /** Open the SSE connection. */
  connect(): void {
    if (!this.isActive) return
    this._open()
  }

  /** Close the SSE connection permanently (no further retries). */
  close(): void {
    this.isActive = false
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.eventSource?.close()
    this.eventSource = null
  }

  private _open(): void {
    try {
      this.eventSource = new EventSource(this.url)

      this.eventSource.onopen = () => {
        this.retryCount = 0
        this.options.onOpen?.()
      }

      this.eventSource.onmessage = (event: MessageEvent) => {
        try {
          const data: unknown = JSON.parse(event.data as string)
          this.options.onMessage(data)
        } catch {
          // Ignore malformed messages
        }
      }

      this.eventSource.onerror = () => {
        this.eventSource?.close()
        this.eventSource = null
        this._handleError()
      }
    } catch {
      this._handleError()
    }
  }

  private _handleError(): void {
    if (!this.isActive) return

    if (this.retryCount < this.maxRetries) {
      const delay = this.retryDelay * Math.pow(2, this.retryCount)
      this.retryCount += 1

      this.options.onError({
        message: 'Connection lost, retrying...',
        retryAttempt: this.retryCount,
        maxRetries: this.maxRetries,
      })

      this.retryTimer = setTimeout(() => {
        if (this.isActive) {
          this._open()
        }
      }, delay)
    } else {
      this.options.onError({
        message: 'Failed to connect after multiple attempts',
        retryAttempt: this.retryCount,
        maxRetries: this.maxRetries,
      })
      this.options.onMaxRetriesExceeded?.()
    }
  }
}
