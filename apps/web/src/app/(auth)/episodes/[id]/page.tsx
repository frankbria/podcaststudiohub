"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession, type Session } from "next-auth/react"
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
  generation_progress: GenerationProgress
  s3_url: string | null
  file_path: string | null
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

interface AuthSession extends Session {
  accessToken?: string
}

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
  const { data: session } = useSession()
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [contentSources, setContentSources] = useState<ContentSource[]>([])
  const [showAddContentDialog, setShowAddContentDialog] = useState(false)
  const [showTTSDialog, setShowTTSDialog] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMessage, setProgressMessage] = useState("")
  const [sseError, setSseError] = useState<string | null>(null)
  const [ttsConfigs, setTtsConfigs] = useState<TTSConfig[]>([])
  const [selectedTtsConfigId, setSelectedTtsConfigId] = useState<string>("")
  const [newTtsProvider, setNewTtsProvider] = useState<string>("openai")
  const [newTtsName, setNewTtsName] = useState<string>("")
  const [savingTts, setSavingTts] = useState(false)

  const getAuthHeaders = useCallback((): Record<string, string> => {
    const token = (session as AuthSession)?.accessToken
    return { Authorization: `Bearer ${token ?? ""}` }
  }, [session])

  const loadEpisode = useCallback(async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}`,
        { headers: getAuthHeaders() }
      )
      if (response.ok) {
        const data = await response.json() as Episode
        setEpisode(data)
        if (data.tts_config_id) {
          setSelectedTtsConfigId(data.tts_config_id)
        }
        if (data.generation_progress?.progress !== undefined) {
          setProgress(data.generation_progress.progress)
        }
      }
    } catch (error) {
      console.error("Failed to load episode:", error)
    }
  }, [params.id, getAuthHeaders])

  const loadContentSources = useCallback(async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/content/episodes/${params.id}/content`,
        { headers: getAuthHeaders() }
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
  }, [params.id, getAuthHeaders])

  const loadTTSConfigs = useCallback(async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/tts-configs`,
        { headers: getAuthHeaders() }
      )
      if (response.ok) {
        const data = await response.json() as { configs?: TTSConfig[] }
        setTtsConfigs(data.configs ?? [])
      }
    } catch (error) {
      console.error("Failed to load TTS configs:", error)
    }
  }, [getAuthHeaders])

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
    if (session) {
      loadEpisode()
      loadContentSources()
      loadTTSConfigs()
    }
  }, [session, loadEpisode, loadContentSources, loadTTSConfigs])

  useEffect(() => {
    if (!episode?.generation_status || !ACTIVE_STATUSES.includes(episode.generation_status)) {
      return
    }

    setSseError(null)
    // EventSource doesn't support custom headers (W3C spec limitation).
    // Pass JWT token as a query parameter so the backend can authenticate the SSE connection.
    const token = (session as AuthSession)?.accessToken
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ""
    const eventSource = new EventSource(
      `${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/progress${tokenParam}`
    )

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data) as {
        status: string
        progress: GenerationProgress
      }
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

      if (newStatus === "complete" || newStatus === "failed") {
        eventSource.close()
        loadEpisode() // Reload to get s3_url and updated fields
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      // Fall back to polling when SSE fails
      const pollInterval = setInterval(() => {
        fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}`,
          { headers: getAuthHeaders() }
        )
          .then((r) => (r.ok ? r.json() : null))
          .then((data: Episode | null) => {
            if (!data) return
            setEpisode(data)
            if (data.generation_progress?.progress !== undefined) {
              setProgress(data.generation_progress.progress)
            }
            if (data.generation_status === "complete" || data.generation_status === "failed") {
              clearInterval(pollInterval)
            }
          })
          .catch(() => {
            // ignore transient poll errors
          })
      }, 3000)
    }

    return () => eventSource.close()
  }, [episode?.generation_status, params.id, session, loadEpisode, getAuthHeaders])

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
        `${process.env.NEXT_PUBLIC_API_URL}/content/episodes/${params.id}/content`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify(body),
        }
      )

      if (response.ok) {
        setShowAddContentDialog(false)
        reset()
        loadContentSources()
      }
    } catch (error) {
      console.error("Failed to add content source:", error)
    }
  }

  const handleDialogOpenChange = (open: boolean) => {
    setShowAddContentDialog(open)
    if (!open) {
      reset()
    }
  }

  const generatePodcast = async () => {
    setGenerating(true)
    setSseError(null)
    setProgress(0)
    setProgressMessage(STATUS_MESSAGES.queued)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/generate`,
        { method: "POST", headers: getAuthHeaders() }
      )
      if (response.ok) {
        loadEpisode()
      }
    } catch (error) {
      console.error("Failed to generate podcast:", error)
    } finally {
      setGenerating(false)
    }
  }

  const saveTTSConfig = async () => {
    if (!newTtsName.trim()) return
    setSavingTts(true)
    try {
      const createResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/tts-configs`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          name: newTtsName,
          provider: newTtsProvider,
          config: DEFAULT_CONFIGS[newTtsProvider] ?? {},
          is_default: false,
        }),
      })
      if (createResponse.ok) {
        const newConfig = await createResponse.json() as TTSConfig
        setTtsConfigs((prev) => [...prev, newConfig])
        setSelectedTtsConfigId(newConfig.id)
        setNewTtsName("")
      }
    } catch (error) {
      console.error("Failed to create TTS config:", error)
    } finally {
      setSavingTts(false)
    }
  }

  const applyTTSConfig = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ tts_config_id: selectedTtsConfigId || null }),
      })
      if (response.ok) {
        await loadEpisode()
        setShowTTSDialog(false)
      }
    } catch (error) {
      console.error("Failed to apply TTS config:", error)
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
                <div className="w-full bg-muted rounded-full h-2.5">
                  <div
                    className="bg-primary h-2.5 rounded-full transition-all"
                    style={{ width: `${progress}%` }}
                  ></div>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {progressMessage || `${progress}% complete`}
                </p>
              </div>
            )}

            {sseError && (
              <p className="text-sm text-destructive mb-4">{sseError}</p>
            )}

            {episode?.generation_status === "failed" &&
              episode.generation_progress?.error_message && (
                <p className="text-sm text-destructive mb-4">
                  Error: {episode.generation_progress.error_message}
                </p>
              )}

            {audioUrl && (
              <div className="mt-4 space-y-2">
                <audio controls className="w-full">
                  <source src={audioUrl} type="audio/mpeg" />
                </audio>
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}/download`}
                  download
                  className="inline-block"
                >
                  <Button variant="outline" size="sm">
                    Download MP3
                  </Button>
                </a>
              </div>
            )}

            {episode?.generation_status === "complete" && !audioUrl && (
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}/download`}
                download
                className="inline-block mt-4"
              >
                <Button variant="outline" size="sm">
                  Download MP3
                </Button>
              </a>
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
              <p className="text-muted-foreground">No content sources added yet</p>
            ) : (
              <ul className="space-y-2">
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
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant={sourceType === "url" ? "default" : "outline"}
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
                  <Label className="mb-1">Saved Configurations</Label>
                  <Select
                    value={selectedTtsConfigId}
                    onValueChange={setSelectedTtsConfigId}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a configuration" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">Default (no override)</SelectItem>
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
                  <Label className="mb-1">Name</Label>
                  <Input
                    value={newTtsName}
                    onChange={(e) => setNewTtsName(e.target.value)}
                    placeholder="My ElevenLabs Config"
                  />
                </div>
                <div>
                  <Label className="mb-1">Provider</Label>
                  <Select value={newTtsProvider} onValueChange={setNewTtsProvider}>
                    <SelectTrigger>
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
                <Button
                  onClick={saveTTSConfig}
                  disabled={savingTts || !newTtsName.trim()}
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
      </div>
    </div>
  )
}
