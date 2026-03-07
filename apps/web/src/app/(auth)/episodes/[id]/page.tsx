"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { contentSourceSchema, type ContentSourceFormData } from "@/lib/validation"

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
  const [isSubmittingContent, setIsSubmittingContent] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isValid },
    reset: resetContentForm,
  } = useForm<ContentSourceFormData>({
    resolver: zodResolver(contentSourceSchema),
    mode: "onBlur",
    defaultValues: {
      sourceType: "url",
    },
  })

  const sourceType = watch("sourceType")

  useEffect(() => {
    if (session) {
      loadEpisode()
      loadContentSources()
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

  const addContentSource = async (data: ContentSourceFormData) => {
    setIsSubmittingContent(true)
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
        resetContentForm()
        loadContentSources()
      }
    } catch (error) {
      console.error("Failed to add content source:", error)
    } finally {
      setIsSubmittingContent(false)
    }
  }

  const handleContentDialogOpenChange = (open: boolean) => {
    setShowAddContentDialog(open)
    if (!open) resetContentForm()
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

        <Dialog open={showAddContentDialog} onOpenChange={handleContentDialogOpenChange}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Content Source</DialogTitle>
              <DialogDescription>Add content to generate your podcast from</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(addContentSource)} className="space-y-4 mt-4">
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={sourceType === "url" ? "default" : "outline"}
                  onClick={() => setValue("sourceType", "url", { shouldValidate: true })}
                >
                  URL
                </Button>
                <Button
                  type="button"
                  variant={sourceType === "text" ? "default" : "outline"}
                  onClick={() => setValue("sourceType", "text", { shouldValidate: true })}
                >
                  Text
                </Button>
              </div>

              {sourceType === "url" ? (
                <div>
                  <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
                    URL <span className="text-red-500">*</span>
                  </label>
                  <Input
                    id="url"
                    type="url"
                    placeholder="https://example.com/article"
                    aria-invalid={errors.url ? "true" : "false"}
                    className={errors.url ? "border-red-500" : ""}
                    {...register("url")}
                  />
                  {errors.url && (
                    <p className="text-red-500 text-sm mt-1">{errors.url.message}</p>
                  )}
                  <p className="text-gray-500 text-xs mt-1">Supports HTTP and HTTPS URLs</p>
                </div>
              ) : (
                <div>
                  <label htmlFor="content" className="block text-sm font-medium text-gray-700 mb-1">
                    Text Content <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    id="content"
                    className={`w-full h-32 p-2 border rounded ${errors.content ? "border-red-500" : ""}`}
                    placeholder="Enter your content here..."
                    aria-invalid={errors.content ? "true" : "false"}
                    {...register("content")}
                  />
                  {errors.content && (
                    <p className="text-red-500 text-sm mt-1">{errors.content.message}</p>
                  )}
                  <p className="text-gray-500 text-xs mt-1">10 - 50,000 characters</p>
                </div>
              )}

              <Button
                type="submit"
                disabled={isSubmittingContent || !isValid}
                className="w-full"
              >
                {isSubmittingContent ? "Adding..." : "Add Content"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
