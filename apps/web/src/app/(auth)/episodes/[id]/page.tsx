"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

interface Episode {
  id: string
  episode_metadata: {
    title: string
    description: string
  }
  generation_status: string
  generation_progress: any
  s3_url: string | null
  file_path: string | null
  project_id: string
  tts_config_id: string | null
}

interface ContentSource {
  id: string
  source_type: string
  source_data: any
  extraction_status: string
}

interface TTSConfig {
  id: string
  name: string
  provider: string
  config: any
  is_default: boolean
}

export default function EpisodePage() {
  const router = useRouter()
  const params = useParams()
  const { data: session } = useSession()
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [contentSources, setContentSources] = useState<ContentSource[]>([])
  const [showAddContentDialog, setShowAddContentDialog] = useState(false)
  const [showTTSDialog, setShowTTSDialog] = useState(false)
  const [contentUrl, setContentUrl] = useState("")
  const [textContent, setTextContent] = useState("")
  const [sourceType, setSourceType] = useState<"url" | "text">("url")
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [ttsConfigs, setTTSConfigs] = useState<TTSConfig[]>([])
  const [selectedTTSConfigId, setSelectedTTSConfigId] = useState<string>("")

  useEffect(() => {
    if (session) {
      loadEpisode()
      loadContentSources()
      loadTTSConfigs()
    }
  }, [session, params.id])

  useEffect(() => {
    if (episode?.generation_status && ["queued", "extracting", "generating", "synthesizing"].includes(episode.generation_status)) {
      // EventSource doesn't support custom headers (W3C spec limitation).
      // Pass JWT token as a query parameter so the backend can authenticate the SSE connection.
      const token = (session as any)?.accessToken
      const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ""
      const eventSource = new EventSource(
        `${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/progress${tokenParam}`
      )

      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data)
        setEpisode((prev) => prev ? { ...prev, generation_status: data.status, generation_progress: data.progress } : null)

        if (data.progress?.progress) {
          setProgress(data.progress.progress)
        }

        if (data.status === "complete" || data.status === "failed") {
          eventSource.close()
          loadEpisode() // Reload to get audio URL
        }
      }

      eventSource.onerror = (error) => {
        console.error("SSE connection error:", error)
        eventSource.close()
      }

      return () => eventSource.close()
    }
  }, [episode?.generation_status, session])

  const loadEpisode = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setEpisode(data)
        if (data.tts_config_id) {
          setSelectedTTSConfigId(data.tts_config_id)
        }
      }
    } catch (error) {
      console.error("Failed to load episode:", error)
    }
  }

  const loadContentSources = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}/content`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        // API returns { content_sources: [...], total: ..., page: ..., ... }
        setContentSources(data.content_sources || [])
      }
    } catch (error) {
      console.error("Failed to load content sources:", error)
    }
  }

  const loadTTSConfigs = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/tts-configs`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setTTSConfigs(data.tts_configs || [])
      }
    } catch (error) {
      console.error("Failed to load TTS configurations:", error)
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

      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}/content`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${(session as any)?.accessToken}`,
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

  const saveTTSConfig = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
        body: JSON.stringify({
          tts_config_id: selectedTTSConfigId || null,
        }),
      })

      if (response.ok) {
        setShowTTSDialog(false)
        loadEpisode()
      }
    } catch (error) {
      console.error("Failed to save TTS configuration:", error)
    }
  }

  const generatePodcast = async () => {
    setGenerating(true)
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/generate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        setProgress(0)
        loadEpisode()
      }
    } catch (error) {
      console.error("Failed to generate podcast:", error)
    } finally {
      setGenerating(false)
    }
  }

  const downloadEpisode = async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${params.id}/download`,
        {
          headers: {
            Authorization: `Bearer ${(session as any)?.accessToken}`,
          },
        }
      )
      if (!response.ok) return
      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = objectUrl
      a.download = `${episode?.episode_metadata?.title || "episode"}.mp3`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(objectUrl)
    } catch (error) {
      console.error("Failed to download episode:", error)
    }
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      draft: "text-gray-600",
      queued: "text-blue-600",
      extracting: "text-yellow-600",
      generating: "text-yellow-600",
      synthesizing: "text-yellow-600",
      uploading: "text-yellow-600",
      complete: "text-green-600",
      failed: "text-red-600",
    }
    return colors[status] || colors.draft
  }

  const isGenerating = episode?.generation_status
    ? ["queued", "extracting", "generating", "synthesizing", "uploading"].includes(episode.generation_status)
    : false

  // Allow generation from draft state or retry after failure
  const canGenerate = contentSources.length > 0
    && (episode?.generation_status === "draft" || episode?.generation_status === "failed")
    && !isGenerating

  const audioUrl = episode?.s3_url || (episode?.file_path ? `${process.env.NEXT_PUBLIC_API_URL}/episodes/${episode.id}/download` : null)

  return (
    <div className="min-h-screen bg-gray-50 p-8">
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
            <div className="flex justify-between items-start">
              <div>
                <CardTitle>{episode?.episode_metadata?.title}</CardTitle>
                <CardDescription>
                  {episode?.episode_metadata?.description}
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={() => setShowTTSDialog(true)}>
                TTS Settings
              </Button>
            </div>
            <CardDescription>
              Status: <span className={getStatusColor(episode?.generation_status || "draft")}>
                {episode?.generation_status || "draft"}
              </span>
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isGenerating && (
              <div className="mb-4">
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div
                    className="bg-blue-600 h-2.5 rounded-full transition-all"
                    style={{ width: `${progress}%` }}
                  ></div>
                </div>
                <p className="text-sm text-gray-600 mt-1">
                  {episode?.generation_progress?.status || `${progress}% complete`}
                </p>
              </div>
            )}

            {audioUrl && episode?.generation_status === "complete" && (
              <div className="mt-4 space-y-3">
                <audio controls className="w-full">
                  <source src={audioUrl} type="audio/mpeg" />
                </audio>
                <Button variant="outline" onClick={downloadEpisode} className="w-full">
                  Download MP3
                </Button>
              </div>
            )}

            {episode?.generation_status === "failed" && (
              <p className="text-sm text-red-600 mt-2">
                {episode?.generation_progress?.error_message || "Generation failed. You can retry below."}
              </p>
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
              <p className="text-gray-600">No content sources added yet</p>
            ) : (
              <ul className="space-y-2">
                {contentSources.map((source) => (
                  <li key={source.id} className="flex items-center justify-between p-3 bg-gray-100 rounded">
                    <div>
                      <span className="font-medium">{source.source_type}</span>
                      <span className="ml-2 text-xs text-gray-500">({source.extraction_status})</span>
                      {source.source_type === "url" && (
                        <p className="text-sm text-gray-600">{source.source_data.url}</p>
                      )}
                      {source.source_type === "text" && (
                        <p className="text-sm text-gray-600">{source.source_data.content?.substring(0, 100)}...</p>
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
          {generating ? "Starting Generation..." : episode?.generation_status === "failed" ? "Retry Generation" : "Generate Podcast"}
        </Button>

        {/* Add Content Dialog */}
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
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    URL
                  </label>
                  <Input
                    value={contentUrl}
                    onChange={(e) => setContentUrl(e.target.value)}
                    placeholder="https://example.com/article"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Text Content
                  </label>
                  <textarea
                    className="w-full h-32 p-2 border rounded"
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

        {/* TTS Settings Dialog */}
        <Dialog open={showTTSDialog} onOpenChange={setShowTTSDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>TTS Settings</DialogTitle>
              <DialogDescription>
                Select a text-to-speech configuration for this episode
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              {ttsConfigs.length === 0 ? (
                <p className="text-gray-600 text-sm">
                  No TTS configurations saved yet. The default provider will be used.
                </p>
              ) : (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700">
                    TTS Configuration
                  </label>
                  <select
                    className="w-full p-2 border rounded"
                    value={selectedTTSConfigId}
                    onChange={(e) => setSelectedTTSConfigId(e.target.value)}
                  >
                    <option value="">Use default provider</option>
                    {ttsConfigs.map((cfg) => (
                      <option key={cfg.id} value={cfg.id}>
                        {cfg.name} ({cfg.provider}){cfg.is_default ? " — default" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <Button onClick={saveTTSConfig} className="w-full">
                Save TTS Settings
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
