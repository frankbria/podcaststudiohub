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
  title: string
  description: string | null
  generation_status: string
  generation_progress: any
  audio_url: string | null
  project_id: string
}

interface ContentSource {
  id: string
  source_type: string
  source_data: any
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

  useEffect(() => {
    if (session) {
      loadEpisode()
      loadContentSources()
    }
  }, [session, params.id])

  useEffect(() => {
    if (episode?.generation_status && ["queued", "extracting", "generating", "synthesizing"].includes(episode.generation_status)) {
      // Start SSE connection for progress updates
      // Note: EventSource doesn't support custom headers, so we rely on cookie-based auth
      const eventSource = new EventSource(
        `${process.env.NEXT_PUBLIC_API_URL}/generation/episodes/${params.id}/progress`
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

      return () => eventSource.close()
    }
  }, [episode?.generation_status])

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
      }
    } catch (error) {
      console.error("Failed to load episode:", error)
    }
  }

  const loadContentSources = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/content/episodes/${params.id}/content`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
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
      draft: "text-gray-600",
      queued: "text-blue-600",
      extracting: "text-yellow-600",
      generating: "text-yellow-600",
      synthesizing: "text-yellow-600",
      complete: "text-green-600",
      failed: "text-red-600",
    }
    return colors[status as keyof typeof colors] || colors.draft
  }

  const canGenerate = contentSources.length > 0 && episode?.generation_status === "draft"

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
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div
                    className="bg-blue-600 h-2.5 rounded-full transition-all"
                    style={{ width: `${progress}%` }}
                  ></div>
                </div>
                <p className="text-sm text-gray-600 mt-1">{progress}% complete</p>
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
              <p className="text-gray-600">No content sources added yet</p>
            ) : (
              <ul className="space-y-2">
                {contentSources.map((source) => (
                  <li key={source.id} className="flex items-center justify-between p-3 bg-gray-100 rounded">
                    <div>
                      <span className="font-medium">{source.source_type}</span>
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
      </div>
    </div>
  )
}
