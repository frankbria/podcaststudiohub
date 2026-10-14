import { useState, useEffect, useRef } from "react"
import { sendAnalyticsEvent, startGeneration } from "./episode-api"
import type { Episode } from "./types"

interface GenerateArgs {
  episodeId: string
  setProgress: (progress: number) => void
  loadEpisode: () => Promise<void>
}

/** The Generate button: restarts progress at 0, then reloads the episode once the backend accepts. */
export function useGeneratePodcast({ episodeId, setProgress, loadEpisode }: GenerateArgs) {
  const [generating, setGenerating] = useState(false)

  const generatePodcast = async () => {
    setGenerating(true)
    setProgress(0)
    try {
      if (await startGeneration(episodeId)) loadEpisode()
    } finally {
      setGenerating(false)
    }
  }

  return { generating, generatePodcast }
}

/** Play/download engagement events; the play event fires once per episode. */
export function useEngagementTracking(episode: Episode | null, episodeId: string) {
  const hasFiredPlayEventRef = useRef(false)

  // App Router reuses this component instance when only the [id] param changes,
  // so the once-per-episode play-event guard must reset on episode navigation.
  useEffect(() => {
    hasFiredPlayEventRef.current = false
  }, [episodeId])

  const track = (eventType: "play" | "download") => {
    if (episode) sendAnalyticsEvent(eventType, episode)
  }

  const handleAudioPlay = () => {
    if (hasFiredPlayEventRef.current) return
    hasFiredPlayEventRef.current = true
    track("play")
  }

  const handleDownloaded = () => track("download")

  return { handleAudioPlay, handleDownloaded }
}
