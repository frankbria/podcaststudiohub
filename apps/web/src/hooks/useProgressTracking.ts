import { useState, useEffect, useRef } from 'react'
import { RobustEventSource, type ConnectionStatus } from '@/lib/event-source-client'

const ACTIVE_STATUSES = ['queued', 'extracting', 'generating', 'synthesizing'] as const
type ActiveStatus = (typeof ACTIVE_STATUSES)[number]

const MAX_RETRIES = 5
const RETRY_DELAY_MS = 1000
const POLLING_INTERVAL_MS = 5000

interface ProgressData {
  status: string
  progress?: { progress?: number }
}

interface UseProgressTrackingOptions {
  /** Full URL to the SSE progress endpoint (including auth token if required). */
  sseUrl: string
  /** Full URL to the HTTP progress endpoint (for polling fallback). */
  pollUrl: string
  /** Authorization Bearer token for polling requests. */
  authToken?: string | null
  /** Called on each progress update. */
  onUpdate: (data: ProgressData) => void
  /** Called when generation is complete or failed. */
  onComplete: () => void
}

interface UseProgressTrackingResult {
  connectionStatus: ConnectionStatus
}

/**
 * Manages real-time progress tracking via SSE with automatic reconnection and
 * a polling fallback.  Activates only while the episode generation_status is
 * in an active state (queued / extracting / generating / synthesizing).
 */
export function useProgressTracking(
  generationStatus: string | undefined,
  options: UseProgressTrackingOptions
): UseProgressTrackingResult {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting')
  const robustESRef = useRef<RobustEventSource | null>(null)
  const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const isActive =
    !!generationStatus && (ACTIVE_STATUSES as readonly string[]).includes(generationStatus)

  useEffect(() => {
    if (!isActive) return

    const { sseUrl, pollUrl, authToken, onUpdate, onComplete } = options

    // -----------------------------------------------------------------------
    // Polling fallback
    // -----------------------------------------------------------------------
    const startPolling = () => {
      setConnectionStatus('polling')

      pollingTimerRef.current = setInterval(async () => {
        try {
          const headers: Record<string, string> = {}
          if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`
          }
          const response = await fetch(pollUrl, { headers })
          if (!response.ok) return

          const data = (await response.json()) as ProgressData
          onUpdate(data)

          if (data.status === 'complete' || data.status === 'failed') {
            if (pollingTimerRef.current !== null) {
              clearInterval(pollingTimerRef.current)
              pollingTimerRef.current = null
            }
            setConnectionStatus('complete')
            onComplete()
          }
        } catch {
          // Polling errors are non-fatal; next interval will retry
        }
      }, POLLING_INTERVAL_MS)
    }

    // -----------------------------------------------------------------------
    // SSE connection
    // -----------------------------------------------------------------------
    robustESRef.current = new RobustEventSource(sseUrl, {
      maxRetries: MAX_RETRIES,
      retryDelay: RETRY_DELAY_MS,

      onOpen: () => setConnectionStatus('connected'),

      onMessage: (raw: unknown) => {
        const data = raw as ProgressData
        setConnectionStatus('connected')
        onUpdate(data)

        if (data.status === 'complete' || data.status === 'failed') {
          robustESRef.current?.close()
          setConnectionStatus('complete')
          onComplete()
        }
      },

      onError: ({ retryAttempt, maxRetries: max }) => {
        setConnectionStatus(retryAttempt < max ? 'reconnecting' : 'error')
      },

      onMaxRetriesExceeded: () => {
        robustESRef.current?.close()
        startPolling()
      },
    })

    robustESRef.current.connect()

    return () => {
      robustESRef.current?.close()
      robustESRef.current = null
      if (pollingTimerRef.current !== null) {
        clearInterval(pollingTimerRef.current)
        pollingTimerRef.current = null
      }
    }
    // Intentionally omit `options` from deps — callers should stabilise callbacks
    // or pass primitive values.  generationStatus drives reconnection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, options.sseUrl])

  return { connectionStatus }
}
