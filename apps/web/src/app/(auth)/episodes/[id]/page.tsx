"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession, type Session } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { RobustEventSource, startPolling, ConnectionStatus } from "@/lib/event-source-manager"

interface AuthSession extends Session {
  accessToken?: string
}

interface GenerationProgress {
  progress?: number
  status?: string
  stage?: string
  error_message?: string
}

interface Episode {
  id: string
  title: string
  description: string | null
  generation_status: string
  generation_progress: GenerationProgress
  audio_url: string | null
  project_id: string
}

interface ContentSource {
  id: string
  source_type: string
  source_data: Record<string, string>
}

export default function EpisodePage() {
  const router = useRouter()
  const params = useParams()
  const { data: session } = useSession()
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [contentSources, setContentSources] = useState<ContentSource[]>([])
  const [showAddContentDialog, setShowAddContentDialog] = useState(false)
  const [contentUrl, setContentUrl] = useState("")
  const [textContent, setTextContent] = useState("")
  const [sourceType, setSourceType] = useState<"url" | "text">("url")
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting")
  const robustESRef = useRef<RobustEventSource | null>(null)
  const stopPollingRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (session) {
      loadEpisode()
      loadContentSources()
    }
  }, [session, params.id])

  useEffect(() => {
    if (
      episode?.generation_status &&
      ["queued", "extracting", "generating", "synthesizing"].includes(episode.generation_status)
    ) {
      // EventSource doesn't support custom headers (W3C spec limitation).
      // Pass JWT token as a query parameter so the backend can authenticate the SSE connection.
      const token = (session as AuthSession)?.accessToken
      const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ""
      const sseUrl = `${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/progress${tokenParam}`

      const handleMessage = (raw: unknown) => {
        const data = raw as { status: string; progress?: { progress?: number } }
        setEpisode((prev) =>
          prev ? { ...prev, generation_status: data.status, generation_progress: data.progress } : null
        )
        if (data.progress?.progress) {
          setProgress(data.progress.progress)
        }
        if (data.status === "complete" || data.status === "failed") {
          setConnectionStatus("complete")
          robustESRef.current?.close()
          stopPollingRef.current?.()
          loadEpisode()
        }
      }

      const handleFallbackToPolling = () => {
        console.warn("SSE max retries exceeded — falling back to polling")
        setConnectionStatus("polling")

        const pollUrl = `${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/progress`
        const fetchInit: RequestInit = token
          ? { headers: { Authorization: `Bearer ${token}` } }
          : {}

        stopPollingRef.current = startPolling({
          url: pollUrl,
          fetchInit,
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
        onStatusChange: setConnectionStatus,
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
    }
  }, [episode?.generation_status, session])

  const loadEpisode = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}`, {
        headers: {
          Authorization: `Bearer ${(session as AuthSession)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setEpisode(data)
      }
    } catch (error) {
      console.error("Failed to load episode:", error)
    }
  }

  const loadContentSources = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/content/episodes/${params.id}/content`, {
        headers: {
          Authorization: `Bearer ${(session as AuthSession)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setContentSources(data)
      }
    } catch (error) {
      console.error("Failed to load content sources:", error)
    }
  }

  const addContentSource = async () => {
    try {
      const body = sourceType === "url"
        ? {
            episode_id: params.id,
            source_type: "url",
            source_data: { url: contentUrl, title: "Web Article" },
          }
        : {
            episode_id: params.id,
            source_type: "text",
            source_data: { content: textContent, title: "Custom Text" },
          }

      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/content/episodes/${params.id}/content`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${(session as AuthSession)?.accessToken}`,
        },
        body: JSON.stringify(body),
      })

      if (response.ok) {
        setShowAddContentDialog(false)
        setContentUrl("")
        setTextContent("")
        loadContentSources()
      }
    } catch (error) {
      console.error("Failed to add content source:", error)
    }
  }

  const generatePodcast = async () => {
    setGenerating(true)
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/generate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${(session as AuthSession)?.accessToken}`,
        },
      })

      if (response.ok) {
        loadEpisode()
      }
    } catch (error) {
      console.error("Failed to generate podcast:", error)
    } finally {
      setGenerating(false)
    }
  }

  const getStatusColor = (status: string) => {
    const colors = {
      draft: "text-muted-foreground",
      queued: "text-primary",
      extracting: "text-accent-foreground",
      generating: "text-accent-foreground",
      synthesizing: "text-accent-foreground",
      complete: "text-foreground",
      failed: "text-destructive",
    }
    return colors[status as keyof typeof colors] || colors.draft
  }

  const canGenerate = contentSources.length > 0 && episode?.generation_status === "draft"

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
            <CardTitle>{episode?.title}</CardTitle>
            <CardDescription>
              Status: <span className={getStatusColor(episode?.generation_status || "draft")}>
                {episode?.generation_status || "draft"}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            {episode?.generation_status && ["queued", "extracting", "generating", "synthesizing"].includes(episode.generation_status) && (
              <div className="mb-4">
                <div className="w-full bg-muted rounded-full h-2.5">
                  <div
                    className="bg-primary h-2.5 rounded-full transition-all"
                    style={{ width: `${progress}%` }}
                  ></div>
                </div>
                <p className="text-sm text-muted-foreground mt-1">{progress}% complete</p>
                <ProgressConnectionStatus status={connectionStatus} />
              </div>
            )}

            {episode?.audio_url && (
              <div className="mt-4">
                <audio controls className="w-full">
                  <source src={episode.audio_url} type="audio/mpeg" />
                </audio>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mb-6">
          <CardHeader>
            <div className="flex justify-between items-center">
              <CardTitle>Content Sources</CardTitle>
              <Button onClick={() => setShowAddContentDialog(true)}>
                Add Content
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {contentSources.length === 0 ? (
              <p className="text-muted-foreground">No content sources added yet</p>
            ) : (
              <ul className="space-y-2">
                {contentSources.map((source) => (
                  <li key={source.id} className="flex items-center justify-between p-3 bg-muted rounded">
                    <div>
                      <span className="font-medium">{source.source_type}</span>
                      {source.source_type === "url" && (
                        <p className="text-sm text-muted-foreground">{source.source_data.url}</p>
                      )}
                      {source.source_type === "text" && (
                        <p className="text-sm text-muted-foreground">{source.source_data.content?.substring(0, 100)}...</p>
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

        <Dialog open={showAddContentDialog} onOpenChange={setShowAddContentDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Content Source</DialogTitle>
              <DialogDescription>Add content to generate your podcast from</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div className="flex gap-2">
                <Button
                  variant={sourceType === "url" ? "default" : "outline"}
                  onClick={() => setSourceType("url")}
                >
                  URL
                </Button>
                <Button
                  variant={sourceType === "text" ? "default" : "outline"}
                  onClick={() => setSourceType("text")}
                >
                  Text
                </Button>
              </div>

              {sourceType === "url" ? (
                <div>
                  <Label className="mb-1">URL</Label>
                  <Input
                    value={contentUrl}
                    onChange={(e) => setContentUrl(e.target.value)}
                    placeholder="https://example.com/article"
                  />
                </div>
              ) : (
                <div>
                  <Label className="mb-1">Text Content</Label>
                  <Textarea
                    className="h-32"
                    value={textContent}
                    onChange={(e) => setTextContent(e.target.value)}
                    placeholder="Enter your content here..."
                  />
                </div>
              )}

              <Button onClick={addContentSource} className="w-full">
                Add Content
              </Button>
            </div>
          </DialogContent>
        </Dialog>
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
