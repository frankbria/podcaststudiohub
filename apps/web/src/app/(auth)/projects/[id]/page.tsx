"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { EditProjectDialog } from "@/components/dialogs/EditProjectDialog"
import { EditEpisodeDialog } from "@/components/dialogs/EditEpisodeDialog"

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
  episode_count: number
  created_at: string
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

  // Project edit/delete state
  const [showEditProject, setShowEditProject] = useState(false)
  const [editProjectLoading, setEditProjectLoading] = useState(false)
  const [showDeleteProject, setShowDeleteProject] = useState(false)
  const [deleteProjectLoading, setDeleteProjectLoading] = useState(false)

  // Episode edit/delete state
  const [editEpisode, setEditEpisode] = useState<Episode | null>(null)
  const [editEpisodeLoading, setEditEpisodeLoading] = useState(false)
  const [deleteEpisode, setDeleteEpisode] = useState<Episode | null>(null)
  const [deleteEpisodeLoading, setDeleteEpisodeLoading] = useState(false)

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

  const handleUpdateProject = async (data: { title: string; description: string }) => {
    if (!project) return
    setEditProjectLoading(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${project.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${(session as any)?.accessToken}`,
          },
          body: JSON.stringify(data),
        }
      )

      if (response.ok) {
        const updated = await response.json()
        setProject((prev) => prev ? { ...prev, ...updated } : prev)
        setShowEditProject(false)
      }
    } catch (error) {
      console.error("Failed to update project:", error)
    } finally {
      setEditProjectLoading(false)
    }
  }

  const handleDeleteProject = async () => {
    if (!project) return
    setDeleteProjectLoading(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${project.id}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${(session as any)?.accessToken}`,
          },
        }
      )

      if (response.ok) {
        router.push("/dashboard")
      }
    } catch (error) {
      console.error("Failed to delete project:", error)
    } finally {
      setDeleteProjectLoading(false)
    }
  }

  const handleUpdateEpisode = async (data: { title: string; description: string }) => {
    if (!editEpisode) return
    setEditEpisodeLoading(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${editEpisode.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${(session as any)?.accessToken}`,
          },
          body: JSON.stringify(data),
        }
      )

      if (response.ok) {
        const updated = await response.json()
        setEpisodes((prev) =>
          prev.map((e) => (e.id === editEpisode.id ? { ...e, ...updated } : e))
        )
        setEditEpisode(null)
      }
    } catch (error) {
      console.error("Failed to update episode:", error)
    } finally {
      setEditEpisodeLoading(false)
    }
  }

  const handleDeleteEpisode = async () => {
    if (!deleteEpisode) return
    setDeleteEpisodeLoading(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${deleteEpisode.id}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${(session as any)?.accessToken}`,
          },
        }
      )

      if (response.ok) {
        setEpisodes((prev) => prev.filter((e) => e.id !== deleteEpisode.id))
        setDeleteEpisode(null)
      }
    } catch (error) {
      console.error("Failed to delete episode:", error)
    } finally {
      setDeleteEpisodeLoading(false)
    }
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
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setShowEditProject(true)}>
              Edit Project
            </Button>
            <Button
              variant="outline"
              onClick={() => setShowDeleteProject(true)}
              className="text-red-600 hover:text-red-700 border-red-300 hover:border-red-400"
            >
              Delete Project
            </Button>
            <Button onClick={() => setShowCreateDialog(true)}>
              Create Episode
            </Button>
          </div>
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
                    <div onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Edit episode"
                        onClick={() => setEditEpisode(episode)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Delete episode"
                        onClick={() => setDeleteEpisode(episode)}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
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

        {project && (
          <EditProjectDialog
            open={showEditProject}
            onOpenChange={setShowEditProject}
            project={project}
            onUpdate={(updated) => setProject(updated)}
            onSave={handleUpdateProject}
            isLoading={editProjectLoading}
          />
        )}

        {project && (
          <ConfirmDeleteDialog
            open={showDeleteProject}
            onOpenChange={setShowDeleteProject}
            title="Delete Project?"
            description="This will permanently remove the project and all its episodes."
            entityName={project.title}
            isLoading={deleteProjectLoading}
            onConfirm={handleDeleteProject}
          />
        )}

        {editEpisode && (
          <EditEpisodeDialog
            open={!!editEpisode}
            onOpenChange={(open) => { if (!open) setEditEpisode(null) }}
            episode={editEpisode}
            onUpdate={(updated) =>
              setEpisodes((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
            }
            onSave={handleUpdateEpisode}
            isLoading={editEpisodeLoading}
          />
        )}

        {deleteEpisode && (
          <ConfirmDeleteDialog
            open={!!deleteEpisode}
            onOpenChange={(open) => { if (!open) setDeleteEpisode(null) }}
            title="Delete Episode?"
            description="This will permanently remove the episode."
            entityName={deleteEpisode.title}
            isLoading={deleteEpisodeLoading}
            onConfirm={handleDeleteEpisode}
          />
        )}
      </div>
    </div>
  )
}
