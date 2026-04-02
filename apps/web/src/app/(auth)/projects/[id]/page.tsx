"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession, type Session } from "next-auth/react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { episodeSchema, type EpisodeFormData } from "@/lib/validation"
import { showSuccessToast, showErrorToast } from "@/lib/toast"
import { EpisodeListSkeleton } from "@/components/skeletons/EpisodeListSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { EditProjectDialog } from "@/components/dialogs/EditProjectDialog"
import { EditEpisodeDialog } from "@/components/dialogs/EditEpisodeDialog"
import { HugeiconsIcon } from "@hugeicons/react"
import { Inbox01Icon, PencilEdit01Icon, Delete02Icon } from "@hugeicons/core-free-icons"

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
  const [showEditProject, setShowEditProject] = useState(false)
  const [editEpisode, setEditEpisode] = useState<Episode | null>(null)
  const [deleteEpisode, setDeleteEpisode] = useState<Episode | null>(null)
  const [isDeletingEpisode, setIsDeletingEpisode] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<EpisodeFormData>({
    resolver: zodResolver(episodeSchema),
    mode: "onChange",
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
      } else {
        showErrorToast("Failed to load project")
      }
    } catch (error) {
      console.error("Failed to load project:", error)
      showErrorToast("Failed to load project: Network error")
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
      } else {
        showErrorToast("Failed to load episodes")
      }
    } catch (error) {
      console.error("Failed to load episodes:", error)
      showErrorToast("Failed to load episodes: Network error")
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
        showSuccessToast("Episode created successfully")
        const episode = await response.json() as Episode
        setShowCreateDialog(false)
        reset()
        router.push(`/episodes/${episode.id}`)
      } else {
        showErrorToast("Failed to create episode: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to create episode:", error)
      showErrorToast("Failed to create episode: Network error")
    }
  }

  const handleDialogOpenChange = (open: boolean) => {
    setShowCreateDialog(open)
    if (!open) {
      reset()
    }
  }

  const handleUpdateProject = async (updated: Project) => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${updated.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({
            title: updated.title,
            description: updated.description,
          }),
        }
      )

      if (response.ok) {
        showSuccessToast("Project updated")
        setShowEditProject(false)
        setProject(updated)
      } else {
        showErrorToast("Failed to update project: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to update project:", error)
      showErrorToast("Failed to update project: Network error")
    }
  }

  const handleUpdateEpisode = async (updated: Episode) => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${updated.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({ title: updated.title }),
        }
      )

      if (response.ok) {
        showSuccessToast("Episode updated")
        setEditEpisode(null)
        setEpisodes((prev) =>
          prev.map((e) => (e.id === updated.id ? { ...e, title: updated.title } : e))
        )
      } else {
        showErrorToast("Failed to update episode: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to update episode:", error)
      showErrorToast("Failed to update episode: Network error")
    }
  }

  const handleConfirmDeleteEpisode = async () => {
    if (!deleteEpisode) return
    setIsDeletingEpisode(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${deleteEpisode.id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${getToken()}` },
        }
      )

      if (response.ok) {
        showSuccessToast("Episode deleted successfully")
        setDeleteEpisode(null)
        setEpisodes((prev) => prev.filter((e) => e.id !== deleteEpisode.id))
      } else {
        showErrorToast("Failed to delete episode: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to delete episode:", error)
      showErrorToast("Failed to delete episode: Network error")
    } finally {
      setIsDeletingEpisode(false)
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
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-6xl mx-auto">
          <EpisodeListSkeleton />
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-6xl mx-auto">
        <Button variant="outline" onClick={() => router.push("/dashboard")} className="mb-4">
          ← Back to Dashboard
        </Button>

        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-2">
            <div>
              <h1 className="text-3xl font-bold">{project?.title}</h1>
              <p className="text-muted-foreground mt-1">{project?.description}</p>
            </div>
            {project && (
              <Button
                variant="ghost"
                size="sm"
                aria-label="Edit project"
                onClick={() => setShowEditProject(true)}
              >
                <HugeiconsIcon icon={PencilEdit01Icon} size={16} />
              </Button>
            )}
          </div>
          <Button onClick={() => setShowCreateDialog(true)}>
            Create Episode
          </Button>
        </div>

        {episodes.length === 0 ? (
          <EmptyState
            icon={<HugeiconsIcon icon={Inbox01Icon} size={64} />}
            title="No episodes in this project"
            description="Create an episode to start generating podcasts"
            action={{
              label: "Create Episode",
              onClick: () => setShowCreateDialog(true),
            }}
          />
        ) : (
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
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      {getStatusBadge(episode.generation_status)}
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Edit ${episode.title}`}
                        onClick={() => setEditEpisode(episode)}
                      >
                        <HugeiconsIcon icon={PencilEdit01Icon} size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Delete ${episode.title}`}
                        onClick={() => setDeleteEpisode(episode)}
                      >
                        <HugeiconsIcon icon={Delete02Icon} size={16} />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
              </Card>
            ))}
          </div>
        )}

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

        {project && (
          <EditProjectDialog
            open={showEditProject}
            onOpenChange={(open) => setShowEditProject(open)}
            project={project}
            onUpdate={handleUpdateProject}
          />
        )}

        {editEpisode && (
          <EditEpisodeDialog
            open={!!editEpisode}
            onOpenChange={(open) => { if (!open) setEditEpisode(null) }}
            episode={editEpisode}
            onUpdate={handleUpdateEpisode}
          />
        )}

        {deleteEpisode && (
          <ConfirmDeleteDialog
            open={!!deleteEpisode}
            onOpenChange={(open) => { if (!open) setDeleteEpisode(null) }}
            title="Delete Episode?"
            description="This will permanently delete the episode and all its content."
            entityName={deleteEpisode.title}
            isLoading={isDeletingEpisode}
            onConfirm={handleConfirmDeleteEpisode}
          />
        )}
      </div>
    </div>
  )
}
