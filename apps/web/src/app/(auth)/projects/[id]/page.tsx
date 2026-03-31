"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession, type Session } from "next-auth/react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { episodeSchema, type EpisodeFormData } from "@/lib/validation"

interface Episode {
  id: string
  title: string
  description: string | null
  generation_status: string
  created_at: string
}

interface Project {
  id: string
  title: string
  description: string | null
}

export default function ProjectPage() {
  const router = useRouter()
  const params = useParams()
  const { data: session } = useSession()
  const [project, setProject] = useState<Project | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<EpisodeFormData>({
    resolver: zodResolver(episodeSchema),
    mode: "onBlur",
  })

  const getToken = useCallback(
    () => (session as Session & { accessToken?: string })?.accessToken ?? "",
    [session]
  )

  const loadProject = useCallback(async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${params.id}`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      )
      if (response.ok) {
        const data = await response.json() as Project
        setProject(data)
      }
    } catch (error) {
      console.error("Failed to load project:", error)
    } finally {
      setLoading(false)
    }
  }, [params.id, getToken])

  const loadEpisodes = useCallback(async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/projects/${params.id}/episodes`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      )
      if (response.ok) {
        const data = await response.json() as { items?: Episode[] }
        setEpisodes(data.items ?? [])
      }
    } catch (error) {
      console.error("Failed to load episodes:", error)
    }
  }, [params.id, getToken])

  useEffect(() => {
    if (session) {
      loadProject()
      loadEpisodes()
    }
  }, [session, loadProject, loadEpisodes])

  const onSubmit = async (data: EpisodeFormData) => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/projects/${params.id}/episodes`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({
            project_id: params.id,
            title: data.title.trim(),
          }),
        }
      )

      if (response.ok) {
        const episode = await response.json() as Episode
        setShowCreateDialog(false)
        reset()
        // Navigate to episode page to add content and generate
        router.push(`/episodes/${episode.id}`)
      }
    } catch (error) {
      console.error("Failed to create episode:", error)
    }
  }

  const handleDialogOpenChange = (open: boolean) => {
    setShowCreateDialog(open)
    if (!open) {
      reset()
    }
  }

  const getStatusBadge = (status: string) => {
    const colors = {
      draft: "bg-muted text-muted-foreground",
      queued: "bg-primary/20 text-primary",
      extracting: "bg-accent text-accent-foreground",
      generating: "bg-accent text-accent-foreground",
      synthesizing: "bg-accent text-accent-foreground",
      complete: "bg-muted text-foreground",
      failed: "bg-destructive/20 text-destructive",
    }

    return (
      <span className={`px-2 py-1 rounded text-xs ${colors[status as keyof typeof colors] || colors.draft}`}>
        {status}
      </span>
    )
  }

  if (loading) {
    return <div className="p-8">Loading...</div>
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-6xl mx-auto">
        <Button variant="outline" onClick={() => router.push("/dashboard")} className="mb-4">
          ← Back to Dashboard
        </Button>

        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold">{project?.title}</h1>
            <p className="text-muted-foreground mt-1">{project?.description}</p>
          </div>
          <Button onClick={() => setShowCreateDialog(true)}>
            Create Episode
          </Button>
        </div>

        <div className="space-y-4">
          {episodes.map((episode) => (
            <Card
              key={episode.id}
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => router.push(`/episodes/${episode.id}`)}
            >
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle>{episode.title}</CardTitle>
                    <CardDescription>{episode.description || "No description"}</CardDescription>
                  </div>
                  {getStatusBadge(episode.generation_status)}
                </div>
              </CardHeader>
            </Card>
          ))}

          {episodes.length === 0 && (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground mb-4">No episodes yet</p>
                <Button onClick={() => setShowCreateDialog(true)}>
                  Create Your First Episode
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        <Dialog open={showCreateDialog} onOpenChange={handleDialogOpenChange}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Episode</DialogTitle>
              <DialogDescription>
                Create a new podcast episode
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
              <div>
                <Label htmlFor="episode-title" className="mb-1">
                  Episode Title <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="episode-title"
                  type="text"
                  placeholder="Episode 1: Introduction"
                  aria-invalid={errors.title ? "true" : "false"}
                  aria-describedby={errors.title ? "episode-title-error" : undefined}
                  {...register("title")}
                  className={errors.title ? "border-destructive" : ""}
                />
                {errors.title && (
                  <p id="episode-title-error" className="text-destructive text-sm mt-1" role="alert">
                    {errors.title.message}
                  </p>
                )}
              </div>
              <Button
                type="submit"
                disabled={isSubmitting || !isValid}
                className="w-full"
              >
                {isSubmitting ? "Creating..." : "Create Episode"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
