import { showSuccessToast, showErrorToast, showWarningToast } from "@/lib/toast"
import { extractApiErrorDetail } from "@/lib/api-error"
import type { ContentSourceFormData } from "@/lib/validation"
import {
  DEFAULT_CONFIGS,
  TTS_DEFAULT_SENTINEL,
  type ContentSource,
  type Episode,
  type EpisodeAnalyticsData,
  type TTSConfig,
} from "./types"

interface ContentSourcesPage {
  content_sources?: ContentSource[]
}
type ContentSourcesResponse = ContentSourcesPage | ContentSource[]

// Backend calls (fetch + EventSource) go through the same-origin /api/proxy
// handler, which injects the bearer token server-side from the httpOnly cookie
// — sent automatically on same-origin requests, so no client token (#212).
// Each fetcher returns null on failure; fetchEpisode has already shown the toast.
export async function fetchEpisode(episodeId: string): Promise<Episode | null> {
  try {
    const response = await fetch(`/api/proxy/episodes/${episodeId}`)
    if (!response.ok) {
      showErrorToast("Failed to load episode")
      return null
    }
    return (await response.json()) as Episode
  } catch (error) {
    console.error("Failed to load episode:", error)
    showErrorToast("Failed to load episode: Network error")
    return null
  }
}

function unwrapSources(data: ContentSourcesResponse): ContentSource[] {
  return Array.isArray(data) ? data : (data.content_sources ?? [])
}

export async function fetchContentSources(episodeId: string): Promise<ContentSource[] | null> {
  try {
    const response = await fetch(`/api/proxy/episodes/${episodeId}/content`)
    if (!response.ok) return null
    const data = await response.json() as ContentSourcesResponse
    // API returns paginated response: { content_sources: [...], total, page, ... }
    return unwrapSources(data)
  } catch (error) {
    console.error("Failed to load content sources:", error)
    return null
  }
}

export async function fetchTTSConfigs(): Promise<TTSConfig[] | null> {
  try {
    const response = await fetch(`/api/proxy/tts-configs`)
    if (!response.ok) return null
    const data = await response.json() as { configs?: TTSConfig[] }
    return data.configs ?? []
  } catch (error) {
    console.error("Failed to load TTS configs:", error)
    return null
  }
}

export async function fetchEpisodeAnalytics(episodeId: string): Promise<EpisodeAnalyticsData | null> {
  try {
    const response = await fetch(`/api/proxy/analytics/episodes/${episodeId}`)
    if (!response.ok) return null
    return (await response.json()) as EpisodeAnalyticsData
  } catch (error) {
    console.error("Failed to load analytics:", error)
    return null
  }
}

/** The response's JSON body, or null when it has none (e.g. a proxy error page). */
async function readJsonBody(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

export type ApprovalResult = { episode: Episode } | { error: string }

/** POST the approval through the same-origin proxy (#576). */
export async function approveContentReview(episodeId: string): Promise<ApprovalResult> {
  try {
    const response = await fetch(
      `/api/proxy/episodes/${episodeId}/content-review/approve`,
      { method: "POST" }
    )
    const body = await readJsonBody(response)
    if (response.ok) return { episode: body as Episode }
    return { error: extractApiErrorDetail(body, response.statusText || "Request failed") }
  } catch {
    return { error: "Network error" }
  }
}

function postPdf(episodeId: string, file: FileList): Promise<Response> {
  // The upload endpoint takes multipart/form-data; the browser sets the
  // Content-Type boundary, so no headers here.
  const formData = new FormData()
  formData.append("file", file[0])
  formData.append("auto_extract", "true")
  return fetch(`/api/proxy/episodes/${episodeId}/content/upload`, { method: "POST", body: formData })
}

function postJsonSource(episodeId: string, data: ContentSourceFormData): Promise<Response> {
  const body = data.sourceType === "url"
    ? {
        episode_id: episodeId,
        source_type: "url",
        source_data: { url: data.url, title: "Web Article" },
      }
    : {
        episode_id: episodeId,
        source_type: "text",
        source_data: { content: data.content, title: "Custom Text" },
      }

  return fetch(`/api/proxy/episodes/${episodeId}/content`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

function postContentSource(episodeId: string, data: ContentSourceFormData): Promise<Response> {
  if (data.sourceType === "pdf") return postPdf(episodeId, data.file!)
  return postJsonSource(episodeId, data)
}

async function reportAddFailure(response: Response): Promise<void> {
  // Backend puts the actionable message (size/format limits) in JSON detail.
  // FastAPI has two shapes for it — HTTPException's string and a 422's
  // array of {msg,loc,type} — and the size/format limits arrive as the
  // array, so extractApiErrorDetail handles both (issue #485, item 1).
  const body = await readJsonBody(response)
  const message = extractApiErrorDetail(body, response.statusText || "Request failed")
  showErrorToast("Failed to add content source: " + message)
}

/** Add a content source; true when the backend accepted it (failures toast). */
export async function submitContentSource(
  episodeId: string,
  data: ContentSourceFormData
): Promise<boolean> {
  try {
    const response = await postContentSource(episodeId, data)
    if (response.ok) {
      showSuccessToast("Content source added")
      return true
    }
    await reportAddFailure(response)
  } catch (error) {
    console.error("Failed to add content source:", error)
    showErrorToast("Failed to add content source: Network error")
  }
  return false
}

/** Delete a content source; true when the backend accepted it (failures toast). */
export async function removeContentSource(sourceId: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/proxy/content/${sourceId}`, { method: "DELETE" })
    if (response.ok) {
      showSuccessToast("Content source deleted")
      return true
    }
    showErrorToast("Failed to delete content source: " + response.statusText)
  } catch (error) {
    console.error("Failed to delete content source:", error)
    showErrorToast("Failed to delete content source: Network error")
  }
  return false
}

async function reportGenerationStarted(response: Response): Promise<void> {
  showSuccessToast("Podcast generation started")
  // Distribution pre-flight warnings (#378): generation proceeds, but
  // e.g. Spotify/Apple were skipped because the RSS feed is missing.
  const data = (await response.json().catch(readNull)) as
    | { warnings?: string[] }
    | null
  data?.warnings?.forEach(showWarning)
}

function readNull(): null {
  return null
}

function showWarning(message: string): void {
  showWarningToast(message)
}

/** Kick off generation; true when it started (failures toast). */
export async function startGeneration(episodeId: string): Promise<boolean> {
  try {
    // Always request distribution (#383): the backend only honors it when
    // ENABLE_PLATFORM_DISTRIBUTION is on AND the project has active
    // distribution targets; otherwise it safely falls through to the normal
    // generation path. Opt-out is per-target via the distribution manager.
    const response = await fetch(
      `/api/proxy/generation/episodes/${episodeId}/generate?enable_distribution=true`,
      { method: "POST" }
    )
    if (response.ok) {
      await reportGenerationStarted(response)
      return true
    }
    showErrorToast("Failed to generate podcast: " + response.statusText)
  } catch (error) {
    console.error("Failed to generate podcast:", error)
    showErrorToast("Failed to generate podcast: Network error")
  }
  return false
}

/** The stored config for a provider, with ElevenLabs voice IDs filled in. */
export function buildTtsConfig(
  provider: string,
  voice1Id: string,
  voice2Id: string
): Record<string, string> {
  const config = { ...(DEFAULT_CONFIGS[provider] ?? {}) }
  if (provider === "elevenlabs") {
    config.voice_1_id = voice1Id.trim()
    config.voice_2_id = voice2Id.trim()
  }
  return config
}

/** Create a TTS config; the saved row, or null on failure (which toasts). */
export async function createTtsConfig(
  name: string,
  provider: string,
  config: Record<string, string>
): Promise<TTSConfig | null> {
  try {
    const response = await fetch(`/api/proxy/tts-configs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, provider, config, is_default: false }),
    })
    if (response.ok) return (await response.json()) as TTSConfig
    showErrorToast("Failed to save TTS configuration")
  } catch (error) {
    console.error("Failed to create TTS config:", error)
    showErrorToast("Failed to save TTS configuration: Network error")
  }
  return null
}

/** Pin (or clear) the episode's TTS config; true when applied (failures toast). */
export async function putEpisodeTtsConfig(
  episodeId: string,
  selectedTtsConfigId: string
): Promise<boolean> {
  try {
    const response = await fetch(`/api/proxy/episodes/${episodeId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tts_config_id:
          selectedTtsConfigId === TTS_DEFAULT_SENTINEL ? null : selectedTtsConfigId,
      }),
    })
    if (response.ok) return true
    showErrorToast("Failed to apply TTS settings")
  } catch (error) {
    console.error("Failed to apply TTS config:", error)
    showErrorToast("Failed to apply TTS settings: Network error")
  }
  return false
}

// Best-effort, fire-and-forget in-app engagement tracking: never blocks the
// UI and never surfaces an error to the user on failure.
export function sendAnalyticsEvent(eventType: "play" | "download", episode: Episode): void {
  fetch("/api/proxy/analytics/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: eventType,
      episode_id: episode.id,
      project_id: episode.project_id,
    }),
  }).catch(readNull)
}
