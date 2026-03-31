"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

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
  const [newEpisodeTitle, setNewEpisodeTitle] = useState("")

  useEffect(() => {
    if (session) {
      loadProject()
      loadEpisodes()
    }
  }, [session, params.id])

  const loadProject = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${params.id}`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setProject(data)
      }
    } catch (error) {
      console.error("Failed to load project:", error)
    } finally {
      setLoading(false)
    }
  }

  const loadEpisodes = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/projects/${params.id}/episodes`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setEpisodes(data.items || [])
      }
    } catch (error) {
      console.error("Failed to load episodes:", error)
    }
  }

  const createEpisode = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/episodes/projects/${params.id}/episodes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
        body: JSON.stringify({
          project_id: params.id,
          title: newEpisodeTitle,
        }),
      })

      if (response.ok) {
        const episode = await response.json()
        setShowCreateDialog(false)
        setNewEpisodeTitle("")
        // Navigate to episode page to add content and generate
        router.push(`/episodes/${episode.id}`)
      }
    } catch (error) {
      console.error("Failed to create episode:", error)
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
      <span
        className={`px-2 py-1 rounded text-xs ${colors[status as keyof typeof colors] || colors.draft}`}
        aria-label={`Status: ${status}`}
      >
        {status}
      </span>
    )
  }

  if (loading) {
    return <div className="p-8" role="status" aria-live="polite">Loading...</div>
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

        <section aria-label="Episodes">
          <div className="space-y-4">
            {episodes.map((episode) => (
              <Card
                key={episode.id}
                className="cursor-pointer hover:shadow-lg transition-shadow focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                role="button"
                tabIndex={0}
                aria-label={`Open episode: ${episode.title}`}
                onClick={() => router.push(`/episodes/${episode.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    router.push(`/episodes/${episode.id}`)
                  }
                }}
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
        </section>

        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent aria-describedby="create-episode-description">
            <DialogHeader>
              <DialogTitle>Create New Episode</DialogTitle>
              <DialogDescription id="create-episode-description">
                Create a new podcast episode
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <Label htmlFor="episode-title" className="mb-1">
                  Episode Title
                </Label>
                <Input
                  id="episode-title"
                  value={newEpisodeTitle}
                  onChange={(e) => setNewEpisodeTitle(e.target.value)}
                  placeholder="Episode 1: Introduction"
                  aria-required="true"
                />
              </div>
              <Button onClick={createEpisode} className="w-full">
                Create Episode
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
