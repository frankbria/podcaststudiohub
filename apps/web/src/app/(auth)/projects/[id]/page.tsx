"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { EditEpisodeDialog, EditableEpisode } from "@/components/dialogs/EditEpisodeDialog"

interface Episode {
  id: string
  title: string
  description: string | null
  generation_status: string
  created_at: string
  project_id: string
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

  // Edit state
  const [editingEpisode, setEditingEpisode] = useState<Episode | null>(null)

  // Delete state
  const [deletingEpisode, setDeletingEpisode] = useState<Episode | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

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

  const handleDeleteEpisode = async () => {
    if (!deletingEpisode) return
    setDeleteLoading(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${deletingEpisode.id}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${(session as any)?.accessToken}`,
          },
        }
      )
      if (!response.ok) {
        throw new Error("Delete request failed")
      }
      setEpisodes((prev) => prev.filter((e) => e.id !== deletingEpisode.id))
      setDeletingEpisode(null)
    } finally {
      setDeleteLoading(false)
    }
  }

  const handleEpisodeUpdated = (updated: EditableEpisode) => {
    setEpisodes((prev) =>
      prev.map((e) =>
        e.id === updated.id ? { ...e, title: updated.title, description: updated.description } : e
      )
    )
    setEditingEpisode(null)
  }

  const getStatusBadge = (status: string) => {
    const colors = {
      draft: "bg-gray-200 text-gray-800",
      queued: "bg-blue-200 text-blue-800",
      extracting: "bg-yellow-200 text-yellow-800",
      generating: "bg-yellow-200 text-yellow-800",
      synthesizing: "bg-yellow-200 text-yellow-800",
      complete: "bg-green-200 text-green-800",
      failed: "bg-red-200 text-red-800",
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
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <Button variant="outline" onClick={() => router.push("/dashboard")} className="mb-4">
          ← Back to Dashboard
        </Button>

        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold">{project?.title}</h1>
            <p className="text-gray-600 mt-1">{project?.description}</p>
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
                  <div className="flex-1 min-w-0">
                    <CardTitle>{episode.title}</CardTitle>
                    <CardDescription>{episode.description || "No description"}</CardDescription>
                  </div>
                  <div className="flex items-center gap-2 ml-2 shrink-0">
                    {getStatusBadge(episode.generation_status)}
                    <div
                      className="flex gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Edit episode"
                        onClick={() => setEditingEpisode(episode)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Delete episode"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => setDeletingEpisode(episode)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                </div>
              </CardHeader>
            </Card>
          ))}

          {episodes.length === 0 && (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-gray-600 mb-4">No episodes yet</p>
                <Button onClick={() => setShowCreateDialog(true)}>
                  Create Your First Episode
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Episode</DialogTitle>
              <DialogDescription>
                Create a new podcast episode
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Episode Title
                </label>
                <Input
                  value={newEpisodeTitle}
                  onChange={(e) => setNewEpisodeTitle(e.target.value)}
                  placeholder="Episode 1: Introduction"
                />
              </div>
              <Button onClick={createEpisode} className="w-full">
                Create Episode
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {editingEpisode && (
          <EditEpisodeDialog
            open={!!editingEpisode}
            onOpenChange={(open) => { if (!open) setEditingEpisode(null) }}
            episode={editingEpisode}
            onUpdate={handleEpisodeUpdated}
            token={(session as any)?.accessToken ?? ""}
          />
        )}

        {deletingEpisode && (
          <ConfirmDeleteDialog
            open={!!deletingEpisode}
            onOpenChange={(open) => { if (!open) setDeletingEpisode(null) }}
            title="Delete Episode?"
            description="This will permanently delete the episode and all its content sources. This action cannot be undone."
            entityName={deletingEpisode.title}
            isLoading={deleteLoading}
            onConfirm={handleDeleteEpisode}
          />
        )}
      </div>
    </div>
  )
}
