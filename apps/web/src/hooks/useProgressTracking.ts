"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { RobustEventSource, ConnectionStatus } from "@/lib/event-source-client"

const ACTIVE_STATUSES = ["queued", "extracting", "generating", "synthesizing"]
const POLL_INTERVAL_MS = 5000
const MAX_RETRIES = 5
const RETRY_DELAY_MS = 1000

interface ProgressData {
  status: string
  progress?: { progress: number }
}

interface UseProgressTrackingOptions {
  episodeId: string
  initialStatus: string
  apiUrl: string
  authToken?: string
  onComplete?: () => void
}

interface UseProgressTrackingResult {
  status: string
  progress: number
  connectionStatus: ConnectionStatus
}

export function useProgressTracking({
  episodeId,
  initialStatus,
  apiUrl,
  authToken,
  onComplete,
}: UseProgressTrackingOptions): UseProgressTrackingResult {
  const [status, setStatus] = useState(initialStatus)
  const [progress, setProgress] = useState(0)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")
  const robustSourceRef = useRef<RobustEventSource | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isActiveRef = useRef(true)

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const handleProgressData = useCallback(
    (data: ProgressData) => {
      setStatus(data.status)
      if (data.progress?.progress !== undefined) {
        setProgress(data.progress.progress)
      }
      if (data.status === "complete" || data.status === "failed") {
        stopPolling()
        setConnectionStatus("complete")
        onComplete?.()
      }
    },
    [stopPolling, onComplete]
  )

  const startPolling = useCallback(() => {
    if (!isActiveRef.current) return

    setConnectionStatus("polling")

    const poll = async () => {
      if (!isActiveRef.current) return
      try {
        const headers: Record<string, string> = {}
        if (authToken) {
          headers["Authorization"] = `Bearer ${authToken}`
        }
        const response = await fetch(
          `${apiUrl}/generation/episodes/${episodeId}/progress`,
          { headers }
        )
        if (response.ok) {
          const data: ProgressData = await response.json()
          handleProgressData(data)
        }
      } catch {
        // Polling errors are non-fatal; we keep trying
      }
    }

    // Poll immediately then on interval
    poll()
    pollTimerRef.current = setInterval(poll, POLL_INTERVAL_MS)
  }, [episodeId, apiUrl, authToken, handleProgressData])

  useEffect(() => {
    if (!ACTIVE_STATUSES.includes(initialStatus)) return

    isActiveRef.current = true

    const tokenParam = authToken ? `?token=${encodeURIComponent(authToken)}` : ""
    const url = `${apiUrl}/generation/episodes/${episodeId}/progress${tokenParam}`

    robustSourceRef.current = new RobustEventSource(url, {
      onMessage: (raw) => {
        handleProgressData(raw as ProgressData)
      },
      onError: (error) => {
        if (error.type === "max_retries_exceeded") {
          // EventSource failed permanently – fall back to polling
          startPolling()
        }
      },
      onStatusChange: (s) => {
        setConnectionStatus(s)
      },
      maxRetries: MAX_RETRIES,
      retryDelay: RETRY_DELAY_MS,
    })

    robustSourceRef.current.connect()

    return () => {
      isActiveRef.current = false
      robustSourceRef.current?.close()
      robustSourceRef.current = null
      stopPolling()
    }
  }, [episodeId, initialStatus]) // eslint-disable-line react-hooks/exhaustive-deps

  return { status, progress, connectionStatus }
}
