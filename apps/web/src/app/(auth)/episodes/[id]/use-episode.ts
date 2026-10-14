import { useState, useEffect, useCallback, useRef } from "react"
import {
  fetchEpisode,
  fetchContentSources,
  fetchTTSConfigs,
  fetchEpisodeAnalytics,
} from "./episode-api"
import {
  TTS_DEFAULT_SENTINEL,
  type ContentSource,
  type Episode,
  type EpisodeAnalyticsData,
  type LoadedAnalytics,
  type TTSConfig,
} from "./types"

interface InitialLoadSinks {
  applyEpisode: (episode: Episode) => void
  setLoading: (loading: boolean) => void
  setContentSources: (sources: ContentSource[]) => void
  setTtsConfigs: (configs: TTSConfig[]) => void
  setLoadedAnalytics: (loaded: LoadedAnalytics) => void
}

// Fetches everything the page needs. Responses that land after the returned
// cleanup ran (unmount, or the App Router swapping [id]) are dropped.
function loadInitialData(episodeId: string, sinks: InitialLoadSinks): () => void {
  let ignore = false
  const live = <T>(sink: (value: T) => void) => (value: T) => {
    if (!ignore) sink(value)
  }
  const present = <T>(sink: (value: T) => void) => (value: T | null) => {
    if (value) sink(value)
  }
  const onEpisode = (data: Episode | null) => {
    if (data) sinks.applyEpisode(data)
    sinks.setLoading(false)
  }
  // Analytics is a supplementary, best-effort section: it has its own
  // contained loading/error state and never blocks or errors the whole page.
  const onAnalytics = (data: EpisodeAnalyticsData | null) => {
    sinks.setLoadedAnalytics({ episodeId, data })
  }

  fetchEpisode(episodeId).then(live(onEpisode))
  fetchContentSources(episodeId).then(live(present(sinks.setContentSources)))
  fetchTTSConfigs().then(live(present(sinks.setTtsConfigs)))
  fetchEpisodeAnalytics(episodeId).then(live(onAnalytics))
  return () => {
    ignore = true
  }
}

function deriveAnalytics(loaded: LoadedAnalytics | null, episodeId: string) {
  if (loaded?.episodeId !== episodeId) {
    return { analytics: null, analyticsLoading: true, analyticsError: false }
  }
  return { analytics: loaded.data, analyticsLoading: false, analyticsError: loaded.data === null }
}

function useIsMounted() {
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])
  return isMountedRef
}

/** The episode and the lists around it (sources, TTS configs, analytics). */
export function useEpisode(episodeId: string, authStatus: string) {
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [loading, setLoading] = useState(true)
  const [contentSources, setContentSources] = useState<ContentSource[]>([])
  const [ttsConfigs, setTtsConfigs] = useState<TTSConfig[]>([])
  const [selectedTtsConfigId, setSelectedTtsConfigId] = useState<string>(TTS_DEFAULT_SENTINEL)
  const [progress, setProgress] = useState(0)
  const [progressMessage, setProgressMessage] = useState("")
  const [loadedAnalytics, setLoadedAnalytics] = useState<LoadedAnalytics | null>(null)
  const isMountedRef = useIsMounted()

  // A fresh server snapshot supersedes any transient SSE progress text: the
  // status-derived default (see the progress <p> in the header card) applies
  // until the stream sends new text.
  const applyEpisode = useCallback((data: Episode) => {
    setEpisode(data)
    setProgressMessage("")
    if (data.tts_config_id) {
      setSelectedTtsConfigId(data.tts_config_id)
    }
    if (data.generation_progress?.progress !== undefined) {
      setProgress(data.generation_progress.progress)
    }
  }, [])

  // Reload paths for event handlers and the SSE stream; the initial load lives
  // in the auth effect below so it can ignore a stale response on unmount or
  // when the App Router swaps [id] on this same instance.
  const loadEpisode = useCallback(async () => {
    const data = await fetchEpisode(episodeId)
    if (!isMountedRef.current) return
    if (data) applyEpisode(data)
    setLoading(false)
  }, [episodeId, applyEpisode, isMountedRef])

  const loadContentSources = useCallback(async () => {
    const sources = await fetchContentSources(episodeId)
    if (sources) setContentSources(sources)
  }, [episodeId])

  useEffect(() => {
    if (authStatus !== "authenticated") return
    return loadInitialData(episodeId, {
      applyEpisode,
      setLoading,
      setContentSources,
      setTtsConfigs,
      setLoadedAnalytics,
    })
  }, [authStatus, episodeId, applyEpisode])

  return {
    episode,
    setEpisode,
    loading,
    contentSources,
    setContentSources,
    ttsConfigs,
    setTtsConfigs,
    selectedTtsConfigId,
    setSelectedTtsConfigId,
    progress,
    setProgress,
    progressMessage,
    setProgressMessage,
    isMountedRef,
    applyEpisode,
    loadEpisode,
    loadContentSources,
    ...deriveAnalytics(loadedAnalytics, episodeId),
  }
}
