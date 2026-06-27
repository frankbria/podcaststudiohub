"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { contentSourceSchema, type ContentSourceFormData } from "@/lib/validation"
import { showSuccessToast, showErrorToast } from "@/lib/toast"
import { RobustEventSource, startPolling, ConnectionStatus } from "@/lib/event-source-manager"
import { AudioPlayerSkeleton } from "@/components/skeletons/AudioPlayerSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { HugeiconsIcon } from "@hugeicons/react"
import { FileEditIcon, Alert02Icon, Delete02Icon } from "@hugeicons/core-free-icons"
import { DownloadButton } from "@/components/DownloadButton"

interface GenerationProgress {
  progress?: number
  status?: string
  stage?: string
  error_message?: string
}

interface Episode {
  id: string
  episode_metadata: { title: string; description: string }
  generation_status: string
  generation_progress?: GenerationProgress
  s3_url: string | null
  project_id: string
  tts_config_id: string | null
  episode_number: number
}

interface ContentSource {
  id: string
  source_type: string
  source_data: Record<string, string>
  extraction_status: string
}

interface TTSConfig {
  id: string
  name: string
  provider: string
  is_default: boolean
}

// Radix <Select.Item> forbids empty-string values, so the "no override" option
// uses a sentinel that maps back to null when applied (#299).
const TTS_DEFAULT_SENTINEL = "__default__"

const ACTIVE_STATUSES = ["queued", "extracting", "generating", "synthesizing", "uploading"]

const STATUS_MESSAGES: Record<string, string> = {
  queued: "Queued for generation...",
  extracting: "Extracting content from sources...",
  generating: "Generating podcast transcript...",
  synthesizing: "Synthesizing audio...",
  uploading: "Uploading audio...",
  complete: "Generation complete",
  failed: "Generation failed",
}

const DEFAULT_CONFIGS: Record<string, Record<string, string>> = {
  openai: { model: "tts-1-hd", voice_1: "alloy", voice_2: "echo" },
  elevenlabs: { model: "eleven_multilingual_v2", voice_1_id: "", voice_2_id: "" },
  gemini: { model: "en-US-Studio-MultiSpeaker", language_code: "en-US" },
  gemini_multi: { model: "en-US-Studio-MultiSpeaker", language_code: "en-US" },
  edge: { voice_1: "en-US-GuyNeural", voice_2: "en-US-JennyNeural" },
}

export default function EpisodePage() {
  const router = useRouter()
  const params = useParams()
  const { status: authStatus } = useSession()
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [loading, setLoading] = useState(true)
  const [contentSources, setContentSources] = useState<ContentSource[]>([])
  const [showAddContentDialog, setShowAddContentDialog] = useState(false)
  const [showTTSDialog, setShowTTSDialog] = useState(false)
  const [deleteContentSource, setDeleteContentSource] = useState<ContentSource | null>(null)
  const [isDeletingContent, setIsDeletingContent] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMessage, setProgressMessage] = useState("")
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")
  const [ttsConfigs, setTtsConfigs] = useState<TTSConfig[]>([])
  const [selectedTtsConfigId, setSelectedTtsConfigId] = useState<string>(TTS_DEFAULT_SENTINEL)
  const [newTtsProvider, setNewTtsProvider] = useState<string>("openai")
  const [newTtsName, setNewTtsName] = useState<string>("")
  const [newTtsVoice1Id, setNewTtsVoice1Id] = useState<string>("")
  const [newTtsVoice2Id, setNewTtsVoice2Id] = useState<string>("")
  const [savingTts, setSavingTts] = useState(false)
  const robustESRef = useRef<RobustEventSource | null>(null)
  const stopPollingRef = useRef<(() => void) | null>(null)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Backend calls (fetch + EventSource) go through the same-origin /api/proxy
  // handler, which injects the bearer token server-side from the httpOnly cookie
  // — sent automatically on same-origin requests, so no client token (#212).
  const loadEpisode = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/proxy/episodes/${params.id}`
      )
      if (response.ok) {
        const data = await response.json() as Episode
        if (!isMountedRef.current) return
        setEpisode(data)
        if (data.tts_config_id) {
          setSelectedTtsConfigId(data.tts_config_id)
        }
        if (data.generation_progress?.progress !== undefined) {
          setProgress(data.generation_progress.progress)
        }
      } else {
        showErrorToast("Failed to load episode")
      }
    } catch (error) {
      console.error("Failed to load episode:", error)
      showErrorToast("Failed to load episode: Network error")
    } finally {
      setLoading(false)
    }
  }, [params.id])

  const loadContentSources = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/proxy/content/episodes/${params.id}/content`
      )
      if (response.ok) {
        const data = await response.json() as { content_sources?: ContentSource[] } | ContentSource[]
        // API returns paginated response: { content_sources: [...], total, page, ... }
        setContentSources(
          Array.isArray(data) ? data : (data.content_sources ?? [])
        )
      }
    } catch (error) {
      console.error("Failed to load content sources:", error)
    }
  }, [params.id])

  const loadTTSConfigs = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/proxy/tts-configs`
      )
      if (response.ok) {
        const data = await response.json() as { configs?: TTSConfig[] }
        setTtsConfigs(data.configs ?? [])
      }
    } catch (error) {
      console.error("Failed to load TTS configs:", error)
    }
  }, [])

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<ContentSourceFormData>({
    resolver: zodResolver(contentSourceSchema),
    mode: "onChange",
    defaultValues: {
      sourceType: "url",
    },
  })

  const sourceType = watch("sourceType")

  useEffect(() => {
    if (authStatus === "authenticated") {
      loadEpisode()
      loadContentSources()
      loadTTSConfigs()
    }
  }, [authStatus, loadEpisode, loadContentSources, loadTTSConfigs])

  useEffect(() => {
    if (!episode?.generation_status || !ACTIVE_STATUSES.includes(episode.generation_status)) {
      return
    }

    setProgressMessage(STATUS_MESSAGES[episode.generation_status] ?? "")

    // EventSource cannot set an Authorization header (W3C spec). Instead of
    // leaking the JWT in the URL, connect to the same-origin /api/proxy Route
    // Handler, which injects the bearer token server-side and streams the SSE
    // response back. The httpOnly session cookie is sent automatically on the
    // same-origin request (#212).
    const sseUrl = `/api/proxy/generation/episodes/${params.id}/progress`

    const handleMessage = (raw: unknown) => {
      if (!isMountedRef.current) return
      const data = raw as { status: string; progress?: GenerationProgress }
      const newStatus = data.status
      const newProgress = data.progress

      setEpisode((prev) =>
        prev ? { ...prev, generation_status: newStatus, generation_progress: newProgress } : null
      )

      if (newProgress?.progress !== undefined) {
        setProgress(newProgress.progress)
      }

      if (newProgress?.status) {
        setProgressMessage(newProgress.status)
      } else if (STATUS_MESSAGES[newStatus]) {
        setProgressMessage(STATUS_MESSAGES[newStatus])
      }

      if (newStatus === "complete") {
        setConnectionStatus("complete")
        robustESRef.current?.close()
        stopPollingRef.current?.()
        showSuccessToast("Podcast generated successfully")
        loadEpisode()
      } else if (newStatus === "failed") {
        setConnectionStatus("complete")
        robustESRef.current?.close()
        stopPollingRef.current?.()
        showErrorToast("Podcast generation failed")
        loadEpisode()
      }
    }

    const handleFallbackToPolling = () => {
      console.warn("SSE max retries exceeded — falling back to polling")
      setConnectionStatus("polling")

      const pollUrl = `/api/proxy/generation/episodes/${params.id}/progress`

      stopPollingRef.current = startPolling({
        url: pollUrl,
        interval: 5000,
        onMessage: handleMessage,
        onError: (err) => console.error("Polling error:", err),
        shouldStop: (data: unknown) => {
          const d = data as { status?: string }
          return d.status === "complete" || d.status === "failed"
        },
      })
    }

    robustESRef.current = new RobustEventSource(sseUrl, {
      onMessage: handleMessage,
      onError: ({ message, attempt, maxRetries }) => {
        console.warn(`SSE error: ${message} (attempt ${attempt}/${maxRetries})`)
      },
      onFallbackToPolling: handleFallbackToPolling,
      onStatusChange: (s) => {
        if (isMountedRef.current) setConnectionStatus(s)
      },
      maxRetries: 5,
      retryDelay: 1000,
    })

    robustESRef.current.connect()

    return () => {
      robustESRef.current?.close()
      robustESRef.current = null
      stopPollingRef.current?.()
      stopPollingRef.current = null
    }
  }, [episode?.generation_status, params.id, loadEpisode])

  const onSubmitContent = async (data: ContentSourceFormData) => {
    try {
      const body = data.sourceType === "url"
        ? {
            episode_id: params.id,
            source_type: "url",
            source_data: { url: data.url, title: "Web Article" },
          }
        : {
            episode_id: params.id,
            source_type: "text",
            source_data: { content: data.content, title: "Custom Text" },
          }

      const response = await fetch(
        `/api/proxy/content/episodes/${params.id}/content`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      )

      if (response.ok) {
        showSuccessToast("Content source added")
        setShowAddContentDialog(false)
        reset()
        loadContentSources()
      } else {
        showErrorToast("Failed to add content source: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to add content source:", error)
      showErrorToast("Failed to add content source: Network error")
    }
  }

  const handleDialogOpenChange = (open: boolean) => {
    setShowAddContentDialog(open)
    if (!open) {
      reset()
    }
  }

  const handleConfirmDeleteContent = async () => {
    if (!deleteContentSource) return
    setIsDeletingContent(true)
    try {
      const response = await fetch(
        `/api/proxy/content/${deleteContentSource.id}`,
        {
          method: "DELETE",
        }
      )

      if (response.ok) {
        showSuccessToast("Content source deleted")
        setDeleteContentSource(null)
        setContentSources((prev) => prev.filter((s) => s.id !== deleteContentSource.id))
      } else {
        showErrorToast("Failed to delete content source: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to delete content source:", error)
      showErrorToast("Failed to delete content source: Network error")
    } finally {
      setIsDeletingContent(false)
    }
  }

  const generatePodcast = async () => {
    setGenerating(true)
    setProgress(0)
    setProgressMessage(STATUS_MESSAGES.queued)
    try {
      const response = await fetch(
        `/api/proxy/generation/episodes/${params.id}/generate`,
        { method: "POST" }
      )
      if (response.ok) {
        showSuccessToast("Podcast generation started")
        loadEpisode()
      } else {
        showErrorToast("Failed to generate podcast: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to generate podcast:", error)
      showErrorToast("Failed to generate podcast: Network error")
    } finally {
      setGenerating(false)
    }
  }

  // ElevenLabs ships with empty voice-ID defaults, so a saved config is only
  // usable once the user provides real voice IDs (#221). Other providers have
  // working defaults and need no extra input.
  const isTtsConfigValid =
    newTtsName.trim() !== "" &&
    (newTtsProvider !== "elevenlabs" ||
      (newTtsVoice1Id.trim() !== "" && newTtsVoice2Id.trim() !== ""))

  const saveTTSConfig = async () => {
    if (!isTtsConfigValid) return
    setSavingTts(true)
    try {
      const config = { ...(DEFAULT_CONFIGS[newTtsProvider] ?? {}) }
      if (newTtsProvider === "elevenlabs") {
        config.voice_1_id = newTtsVoice1Id.trim()
        config.voice_2_id = newTtsVoice2Id.trim()
      }
      const createResponse = await fetch(`/api/proxy/tts-configs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newTtsName,
          provider: newTtsProvider,
          config,
          is_default: false,
        }),
      })
      if (createResponse.ok) {
        const newConfig = await createResponse.json() as TTSConfig
        setTtsConfigs((prev) => [...prev, newConfig])
        setSelectedTtsConfigId(newConfig.id)
        setNewTtsName("")
        setNewTtsVoice1Id("")
        setNewTtsVoice2Id("")
        showSuccessToast("TTS configuration saved")
      } else {
        showErrorToast("Failed to save TTS configuration")
      }
    } catch (error) {
      console.error("Failed to create TTS config:", error)
      showErrorToast("Failed to save TTS configuration: Network error")
    } finally {
      setSavingTts(false)
    }
  }

  const applyTTSConfig = async () => {
    try {
      const response = await fetch(`/api/proxy/episodes/${params.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tts_config_id:
            selectedTtsConfigId === TTS_DEFAULT_SENTINEL ? null : selectedTtsConfigId,
        }),
      })
      if (response.ok) {
        showSuccessToast("TTS settings applied")
        await loadEpisode()
        setShowTTSDialog(false)
      } else {
        showErrorToast("Failed to apply TTS settings")
      }
    } catch (error) {
      console.error("Failed to apply TTS config:", error)
      showErrorToast("Failed to apply TTS settings: Network error")
    }
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      draft: "text-muted-foreground",
      queued: "text-primary",
      extracting: "text-accent-foreground",
      generating: "text-accent-foreground",
      synthesizing: "text-accent-foreground",
      uploading: "text-accent-foreground",
      complete: "text-foreground",
      failed: "text-destructive",
    }
    return colors[status] ?? colors.draft
  }

  const isActiveStatus = ACTIVE_STATUSES.includes(episode?.generation_status ?? "")
  const canGenerate =
    contentSources.length > 0 && episode?.generation_status === "draft"

  const episodeTitle = episode?.episode_metadata?.title ?? "Episode"
  const audioUrl = episode?.s3_url ?? null

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-4xl mx-auto">
          <AudioPlayerSkeleton />
        </div>
      </div>
    )
  }

  if (!episode) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-4xl mx-auto">
          <EmptyState
            icon={<HugeiconsIcon icon={Alert02Icon} size={64} />}
            title="Episode not found"
            description="This episode could not be loaded. Please try again."
            action={{
              label: "Back",
              onClick: () => router.back(),
            }}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-4xl mx-auto">
        <Button
          variant="outline"
          onClick={() => router.push(`/projects/${episode?.project_id}`)}
          className="mb-4"
        >
          ← Back to Project
        </Button>

        <Card className="mb-6">
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>{episodeTitle}</CardTitle>
                <CardDescription>
                  Status:{" "}
                  <span className={getStatusColor(episode?.generation_status ?? "draft")}>
                    {episode?.generation_status ?? "draft"}
                  </span>
                </CardDescription>
              </div>
              <Button variant="outline" onClick={() => setShowTTSDialog(true)} size="sm">
                TTS Settings
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {isActiveStatus && (
              <div className="mb-4">
                <div
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Generation progress"
                  className="w-full bg-muted rounded-full h-2.5"
                >
                  <div
                    className="bg-primary h-2.5 rounded-full transition-all"
                    style={{ width: `${progress}%` }}
                  ></div>
                </div>
                <p className="text-sm text-muted-foreground mt-1" aria-live="polite">
                  {progressMessage || `${progress}% complete`}
                </p>
                <ProgressConnectionStatus status={connectionStatus} />
              </div>
            )}

            {episode?.generation_status === "failed" &&
              episode.generation_progress?.error_message && (
                <p className="text-sm text-destructive mb-4">
                  Error: {episode.generation_progress.error_message}
                </p>
              )}

            {audioUrl && (
              <div className="mt-4 space-y-2">
                <audio controls className="w-full" aria-label={`Podcast audio: ${episodeTitle}`}>
                  <source src={audioUrl} type="audio/mpeg" />
                </audio>
                <DownloadButton
                  audioUrl={audioUrl}
                  episodeTitle={episodeTitle}
                  isLoading={generating}
                />
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardHeader>
            <div className="flex justify-between items-center">
              <CardTitle>Content Sources</CardTitle>
              <Button onClick={() => setShowAddContentDialog(true)}>Add Content</Button>
            </div>
          </CardHeader>
          <CardContent>
            {contentSources.length === 0 ? (
              <EmptyState
                icon={<HugeiconsIcon icon={FileEditIcon} size={48} />}
                title="No content added yet"
                description="Add a URL or text content to generate your podcast"
                action={{
                  label: "Add Content",
                  onClick: () => setShowAddContentDialog(true),
                }}
              />
            ) : (
              <ul className="space-y-2" aria-label="Content sources">
                {contentSources.map((source) => (
                  <li
                    key={source.id}
                    className="flex items-center justify-between p-3 bg-muted rounded"
                  >
                    <div>
                      <span className="font-medium">{source.source_type}</span>
                      {source.extraction_status && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({source.extraction_status})
                        </span>
                      )}
                      {source.source_type === "url" && (
                        <p className="text-sm text-muted-foreground">{source.source_data.url}</p>
                      )}
                      {source.source_type === "text" && (
                        <p className="text-sm text-muted-foreground">
                          {source.source_data.content?.substring(0, 100)}...
                        </p>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Delete content source"
                      onClick={() => setDeleteContentSource(source)}
                    >
                      <HugeiconsIcon icon={Delete02Icon} size={16} />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Button
          onClick={generatePodcast}
          disabled={!canGenerate || generating}
          className="w-full"
          size="lg"
        >
          {generating ? "Starting Generation..." : "Generate Podcast"}
        </Button>

        {/* Add Content Dialog */}
        <Dialog open={showAddContentDialog} onOpenChange={handleDialogOpenChange}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Content Source</DialogTitle>
              <DialogDescription>Add content to generate your podcast from</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmitContent)} className="space-y-4 mt-4" noValidate>
              <div>
                <Label className="mb-2">Content Type</Label>
                <div className="flex gap-2" role="group" aria-label="Content source type">
                  <Button
                    type="button"
                    variant={sourceType === "url" ? "default" : "outline"}
                    aria-pressed={sourceType === "url"}
                    onClick={() => {
                      setValue("sourceType", "url", { shouldValidate: true })
                    }}
                    className="flex-1"
                  >
                    URL
                  </Button>
                  <Button
                    type="button"
                    variant={sourceType === "text" ? "default" : "outline"}
                    aria-pressed={sourceType === "text"}
                    onClick={() => {
                      setValue("sourceType", "text", { shouldValidate: true })
                    }}
                    className="flex-1"
                  >
                    Text
                  </Button>
                </div>
              </div>

              {sourceType === "url" ? (
                <div>
                  <Label htmlFor="content-url" className="mb-1">
                    URL <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="content-url"
                    type="url"
                    placeholder="https://example.com/article"
                    aria-invalid={errors.url ? "true" : "false"}
                    aria-describedby={errors.url ? "content-url-error" : undefined}
                    {...register("url")}
                    className={errors.url ? "border-destructive" : ""}
                  />
                  {errors.url && (
                    <p id="content-url-error" className="text-destructive text-sm mt-1" role="alert">
                      {errors.url.message}
                    </p>
                  )}
                  <p className="text-muted-foreground text-xs mt-1">
                    Supports HTTP, HTTPS, and YouTube URLs
                  </p>
                </div>
              ) : (
                <div>
                  <Label htmlFor="content-text" className="mb-1">
                    Text Content <span className="text-destructive">*</span>
                  </Label>
                  <Textarea
                    id="content-text"
                    className={`h-32 ${errors.content ? "border-destructive" : ""}`}
                    placeholder="Enter your content here..."
                    aria-invalid={errors.content ? "true" : "false"}
                    aria-describedby={errors.content ? "content-text-error" : undefined}
                    {...register("content")}
                  />
                  {errors.content && (
                    <p id="content-text-error" className="text-destructive text-sm mt-1" role="alert">
                      {errors.content.message}
                    </p>
                  )}
                  <p className="text-muted-foreground text-xs mt-1">
                    10 – 50,000 characters
                  </p>
                </div>
              )}

              <Button
                type="submit"
                disabled={isSubmitting || !isValid}
                className="w-full"
              >
                {isSubmitting ? "Adding..." : "Add Content"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* TTS Settings Dialog */}
        <Dialog open={showTTSDialog} onOpenChange={setShowTTSDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>TTS Settings</DialogTitle>
              <DialogDescription>
                Select a text-to-speech provider for this episode
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              {ttsConfigs.length > 0 && (
                <div>
                  <Label htmlFor="tts-config-select" className="mb-1">Saved Configurations</Label>
                  <Select
                    value={selectedTtsConfigId}
                    onValueChange={setSelectedTtsConfigId}
                  >
                    <SelectTrigger id="tts-config-select" aria-label="Select a saved TTS configuration">
                      <SelectValue placeholder="Select a configuration" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={TTS_DEFAULT_SENTINEL}>Default (no override)</SelectItem>
                      {ttsConfigs.map((cfg) => (
                        <SelectItem key={cfg.id} value={cfg.id}>
                          {cfg.name} ({cfg.provider})
                          {cfg.is_default ? " — default" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="border rounded p-3 space-y-3">
                <p className="text-sm font-medium">Create New Configuration</p>
                <div>
                  <Label htmlFor="new-tts-name" className="mb-1">Name</Label>
                  <Input
                    id="new-tts-name"
                    value={newTtsName}
                    onChange={(e) => setNewTtsName(e.target.value)}
                    placeholder="My ElevenLabs Config"
                    aria-required="true"
                  />
                </div>
                <div>
                  <Label htmlFor="new-tts-provider" className="mb-1">Provider</Label>
                  <Select value={newTtsProvider} onValueChange={setNewTtsProvider}>
                    <SelectTrigger id="new-tts-provider" aria-label="Select TTS provider">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="openai">OpenAI</SelectItem>
                      <SelectItem value="elevenlabs">ElevenLabs</SelectItem>
                      <SelectItem value="gemini">Gemini</SelectItem>
                      <SelectItem value="gemini_multi">Gemini Multi-Speaker</SelectItem>
                      <SelectItem value="edge">Edge TTS (Free)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {newTtsProvider === "elevenlabs" && (
                  <>
                    <div>
                      <Label htmlFor="new-tts-voice-1" className="mb-1">Voice 1 ID</Label>
                      <Input
                        id="new-tts-voice-1"
                        value={newTtsVoice1Id}
                        onChange={(e) => setNewTtsVoice1Id(e.target.value)}
                        placeholder="21m00Tcm4TlvDq8ikWAM"
                        aria-required="true"
                      />
                    </div>
                    <div>
                      <Label htmlFor="new-tts-voice-2" className="mb-1">Voice 2 ID</Label>
                      <Input
                        id="new-tts-voice-2"
                        value={newTtsVoice2Id}
                        onChange={(e) => setNewTtsVoice2Id(e.target.value)}
                        placeholder="AZnzlk1XvdvUeBnXmlld"
                        aria-required="true"
                      />
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Required ElevenLabs voice IDs from your ElevenLabs account (Voice Library).
                    </p>
                  </>
                )}
                <Button
                  onClick={saveTTSConfig}
                  disabled={savingTts || !isTtsConfigValid}
                  variant="outline"
                  className="w-full"
                >
                  {savingTts ? "Saving..." : "Save Configuration"}
                </Button>
              </div>

              <Button onClick={applyTTSConfig} className="w-full">
                Apply to Episode
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {deleteContentSource && (
          <ConfirmDeleteDialog
            open={!!deleteContentSource}
            onOpenChange={(open) => { if (!open) setDeleteContentSource(null) }}
            title="Delete Content Source?"
            description="This will permanently remove this content source from the episode."
            entityName={
              deleteContentSource.source_type === "url"
                ? (deleteContentSource.source_data.url ?? "content source")
                : "text content"
            }
            isLoading={isDeletingContent}
            onConfirm={handleConfirmDeleteContent}
          />
        )}
      </div>
    </div>
  )
}

interface ProgressConnectionStatusProps {
  status: ConnectionStatus
}

function ProgressConnectionStatus({ status }: ProgressConnectionStatusProps) {
  const statusConfig: Record<ConnectionStatus, { indicator: string; text: string; className: string }> = {
    connecting: { indicator: "●", text: "Connecting...", className: "text-primary" },
    connected: { indicator: "●", text: "Connected", className: "text-foreground" },
    reconnecting: { indicator: "●", text: "Reconnecting...", className: "text-accent-foreground" },
    error: { indicator: "●", text: "Connection lost, retrying...", className: "text-destructive" },
    polling: { indicator: "●", text: "Using polling mode", className: "text-accent-foreground" },
    complete: { indicator: "●", text: "Generation complete", className: "text-foreground" },
  }

  const config = statusConfig[status]
  if (!config) return null

  return (
    <p className={`text-xs mt-1 flex items-center gap-1 ${config.className}`}>
      <span aria-hidden="true">{config.indicator}</span>
      {config.text}
    </p>
  )
}
