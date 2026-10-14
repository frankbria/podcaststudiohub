export interface ContentFlag {
  kind: "domain" | "promotion"
  match: string
  turn: number
  speaker: "host" | "guest"
}

export interface GenerationProgress {
  progress?: number
  status?: string
  stage?: string
  error_message?: string
  // Set by the backend's script screening (#576): a script that mentions a
  // domain or promotion its sources don't support is held from the RSS feed
  // and platform distribution until the owner approves it.
  content_flags?: ContentFlag[]
  content_review?: "pending" | "approved" | null
}

export interface Episode {
  id: string
  episode_metadata: { title: string; description: string }
  generation_status: string
  generation_progress?: GenerationProgress
  s3_url: string | null
  project_id: string
  tts_config_id: string | null
  episode_number: number
}

export interface ContentSource {
  id: string
  source_type: string
  source_data: Record<string, string>
  extraction_status: string
}

export interface TTSConfig {
  id: string
  name: string
  provider: string
  is_default: boolean
}

export interface EpisodeAnalyticsMetrics {
  total_downloads: number
  total_plays: number
  total_streams: number
  average_listen_duration_seconds: number
  // Fraction 0-1 (see apps/api/src/services/analytics_service.py) — scaled to
  // 0-100 before rendering, since <Progress> expects a percentage.
  completion_rate: number
}

export interface EpisodeAnalyticsData {
  episode_id: string
  period: { from: string; to: string }
  metrics: EpisodeAnalyticsMetrics
  device_breakdown: { mobile: number; desktop: number; tablet: number; unknown: number }
  app_breakdown: Record<string, number>
  top_countries: Array<{ country: string; downloads: number }>
}

// The loaded analytics remember which episode they belong to, so the
// section's loading/error state is derived and resets whenever the App
// Router swaps [id] on this same instance.
export interface LoadedAnalytics {
  episodeId: string
  data: EpisodeAnalyticsData | null
}

// Radix <Select.Item> forbids empty-string values, so the "no override" option
// uses a sentinel that maps back to null when applied (#299).
export const TTS_DEFAULT_SENTINEL = "__default__"

export const ACTIVE_STATUSES = [
  "queued",
  "extracting",
  "generating",
  "synthesizing",
  "composing",
  "uploading",
  "distributing",
]

export const STATUS_MESSAGES: Record<string, string> = {
  queued: "Queued for generation...",
  extracting: "Extracting content from sources...",
  generating: "Generating podcast transcript...",
  synthesizing: "Synthesizing audio...",
  composing: "Composing final audio...",
  uploading: "Uploading audio...",
  distributing: "Distributing to platforms...",
  distribution_failed: "Distribution failed",
  complete: "Generation complete",
  failed: "Generation failed",
}

// `model` is required by the backend write schema, so whatever is stored here
// is what every new config carries -- there is no "unset" for the engine to
// fall back from. These were podcastfy-era values that the in-repo TTS layer
// (#542) cannot use: `eleven_multilingual_v2` has no Text-to-Dialogue support,
// and `en-US-Studio-MultiSpeaker` is a restricted *voice* name sitting in a
// field that wants a model id. The backends defend against the old values for
// rows already written; these are what new rows should carry.
export const DEFAULT_CONFIGS: Record<string, Record<string, string>> = {
  openai: { model: "gpt-4o-mini-tts", voice_1: "alloy", voice_2: "echo" },
  elevenlabs: { model: "eleven_v3", voice_1_id: "", voice_2_id: "" },
  gemini: { model: "gemini-2.5-flash-tts", language_code: "en-US" },
  gemini_multi: { model: "gemini-2.5-flash-tts", language_code: "en-US" },
  edge: { voice_1: "en-US-GuyNeural", voice_2: "en-US-JennyNeural" },
}

export function isActiveStatus(status: string | undefined): boolean {
  return ACTIVE_STATUSES.includes(status ?? "")
}

export type DeviceBreakdownData = EpisodeAnalyticsData["device_breakdown"]
export type TopCountriesData = EpisodeAnalyticsData["top_countries"]
