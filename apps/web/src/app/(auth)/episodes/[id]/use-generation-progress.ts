import { useState, useEffect, type Dispatch, type SetStateAction } from "react"
import { showSuccessToast, showErrorToast } from "@/lib/toast"
import { RobustEventSource, startPolling, type ConnectionStatus } from "@/lib/event-source-manager"
import {
  STATUS_MESSAGES,
  isActiveStatus,
  type Episode,
  type GenerationProgress,
} from "./types"

interface ProgressMessage {
  status: string
  progress?: GenerationProgress
}

interface StreamSinks {
  isMounted: () => boolean
  onUpdate: (message: ProgressMessage) => void
  setConnection: (status: ConnectionStatus) => void
  reload: () => void
}

// A terminal status ends the run: the stream closes and the toast matches.
const TERMINAL_NOTIFIERS = new Map<string, () => void>([
  ["complete", () => showSuccessToast("Podcast generated successfully")],
  ["failed", () => showErrorToast("Podcast generation failed")],
])

function isTerminalMessage(data: unknown): boolean {
  return TERMINAL_NOTIFIERS.has((data as ProgressMessage).status)
}

interface SseErrorInfo {
  message: string
  attempt: number
  maxRetries: number
}

function logSseError({ message, attempt, maxRetries }: SseErrorInfo) {
  console.warn(`SSE error: ${message} (attempt ${attempt}/${maxRetries})`)
}

function logPollingError(err: unknown) {
  console.error("Polling error:", err)
}

// EventSource cannot set an Authorization header (W3C spec). Instead of
// leaking the JWT in the URL, connect to the same-origin /api/proxy Route
// Handler, which injects the bearer token server-side and streams the SSE
// response back. The httpOnly session cookie is sent automatically on the
// same-origin request (#212).
function openProgressStream(episodeId: string, sinks: StreamSinks): () => void {
  const url = `/api/proxy/generation/episodes/${episodeId}/progress`
  let stopPolling: (() => void) | null = null

  const handleMessage = (raw: unknown) => {
    if (!sinks.isMounted()) return
    const message = raw as ProgressMessage
    sinks.onUpdate(message)

    const notify = TERMINAL_NOTIFIERS.get(message.status)
    if (!notify) return
    sinks.setConnection("complete")
    source?.close()
    stopPolling?.()
    notify()
    sinks.reload()
  }

  const handleFallbackToPolling = () => {
    console.warn("SSE max retries exceeded — falling back to polling")
    sinks.setConnection("polling")
    stopPolling = startPolling({
      url,
      interval: 5000,
      onMessage: handleMessage,
      onError: logPollingError,
      shouldStop: isTerminalMessage,
    })
  }

  const handleStatusChange = (status: ConnectionStatus) => {
    if (sinks.isMounted()) sinks.setConnection(status)
  }

  let source: RobustEventSource | null = new RobustEventSource(url, {
    onMessage: handleMessage,
    onError: logSseError,
    onFallbackToPolling: handleFallbackToPolling,
    onStatusChange: handleStatusChange,
    maxRetries: 5,
    retryDelay: 1000,
  })
  source.connect()

  return () => {
    source?.close()
    source = null
    stopPolling?.()
    stopPolling = null
  }
}

function mergeProgress(
  prev: Episode | null,
  status: string,
  progress: GenerationProgress | undefined
): Episode | null {
  if (!prev) return null
  return { ...prev, generation_status: status, generation_progress: progress }
}

interface ProgressSetters {
  setEpisode: Dispatch<SetStateAction<Episode | null>>
  setProgress: (progress: number) => void
  setProgressMessage: (message: string) => void
}

function applyProgressValue(progress: GenerationProgress | undefined, setters: ProgressSetters) {
  if (progress?.progress !== undefined) {
    setters.setProgress(progress.progress)
  }
}

function applyProgressMessage(
  status: string,
  progress: GenerationProgress | undefined,
  setters: ProgressSetters
) {
  if (progress?.status) {
    setters.setProgressMessage(progress.status)
  } else if (STATUS_MESSAGES[status]) {
    setters.setProgressMessage(STATUS_MESSAGES[status])
  }
}

function applyProgressUpdate({ status, progress }: ProgressMessage, setters: ProgressSetters) {
  const merge = (prev: Episode | null) => mergeProgress(prev, status, progress)
  setters.setEpisode(merge)
  applyProgressValue(progress, setters)
  applyProgressMessage(status, progress, setters)
}

interface UseGenerationProgressArgs extends ProgressSetters {
  episodeId: string
  status: string | undefined
  isMountedRef: { current: boolean }
  loadEpisode: () => Promise<void>
}

/** Live connection state for an in-flight generation, wiring SSE (then polling) into the episode state. */
export function useGenerationProgress({
  episodeId,
  status,
  isMountedRef,
  loadEpisode,
  setEpisode,
  setProgress,
  setProgressMessage,
}: UseGenerationProgressArgs): ConnectionStatus {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")

  useEffect(() => {
    if (!isActiveStatus(status)) return
    const setters = { setEpisode, setProgress, setProgressMessage }
    return openProgressStream(episodeId, {
      isMounted: () => isMountedRef.current,
      onUpdate: (message) => applyProgressUpdate(message, setters),
      setConnection: setConnectionStatus,
      reload: loadEpisode,
    })
  }, [status, episodeId, isMountedRef, loadEpisode, setEpisode, setProgress, setProgressMessage])

  return connectionStatus
}
