"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
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
import { EditEpisodeDialog, type Episode as EditableEpisode } from "@/components/dialogs/EditEpisodeDialog"
import { HugeiconsIcon } from "@hugeicons/react"
import { InboxIcon, PencilEdit01Icon, Delete02Icon, Analytics01Icon, RssIcon } from "@hugeicons/core-free-icons"

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
  const { status: authStatus } = useSession()
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

  // Backend calls go through the same-origin /api/proxy handler, which injects
  // the bearer token server-side from the httpOnly cookie — no client token (#212).
  const loadProject = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/proxy/projects/${params.id}`
      )
      if (response.ok) {
        // API returns `name`; map to this view-model's `title` (issue #337).
        const data = await response.json() as { id: string; name: string; description: string | null }
        setProject({ id: data.id, title: data.name, description: data.description })
      } else {
        showErrorToast("Failed to load project")
      }
    } catch (error) {
      console.error("Failed to load project:", error)
      showErrorToast("Failed to load project: Network error")
    } finally {
      setLoading(false)
    }
  }, [params.id])

  const loadEpisodes = useCallback(async () => {
    try {
      const response = await fetch(
        `/api/proxy/episodes?project_id=${params.id}`
      )
      if (response.ok) {
        // API returns {episodes: [...]} with nested episode_metadata; flatten to
        // this view-model's title/description (issue #337).
        const data = await response.json() as {
          episodes?: Array<{
            id: string
            episode_metadata?: { title?: string; description?: string | null }
            generation_status: string
            created_at: string
          }>
        }
        setEpisodes(
          (data.episodes ?? []).map((e) => ({
            id: e.id,
            title: e.episode_metadata?.title ?? "",
            description: e.episode_metadata?.description ?? null,
            generation_status: e.generation_status,
            created_at: e.created_at,
          }))
        )
      } else {
        showErrorToast("Failed to load episodes")
      }
    } catch (error) {
      console.error("Failed to load episodes:", error)
      showErrorToast("Failed to load episodes: Network error")
    }
  }, [params.id])

  useEffect(() => {
    if (authStatus === "authenticated") {
      loadProject()
      loadEpisodes()
    }
  }, [authStatus, loadProject, loadEpisodes])

  const onSubmit = async (data: EpisodeFormData) => {
    try {
      const response = await fetch(
        `/api/proxy/episodes`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            // API stores episode fields under nested episode_metadata (issue #337).
            project_id: params.id,
            episode_metadata: { title: data.title.trim() },
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
        `/api/proxy/projects/${updated.id}`,
        {
          method: "PUT",  // API exposes PUT for project update (issue #337)
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: updated.title,
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

  const handleUpdateEpisode = async (updated: EditableEpisode) => {
    try {
      const response = await fetch(
        `/api/proxy/episodes/${updated.id}`,
        {
          method: "PUT",  // API exposes PUT for episode update (issue #337)
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ episode_metadata: { title: updated.title } }),
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
        `/api/proxy/episodes/${deleteEpisode.id}`,
        {
          method: "DELETE",
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
      composing: "bg-accent text-accent-foreground",
      uploading: "bg-accent text-accent-foreground",
      distributing: "bg-accent text-accent-foreground",
      distribution_failed: "bg-destructive/20 text-destructive",
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

        <nav className="flex gap-4 mb-4">
          <a
            href={`/projects/${params.id}/analytics`}
            className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
          >
            <HugeiconsIcon icon={Analytics01Icon} size={16} />
            Analytics
          </a>
          <a
            href={`/projects/${params.id}/distribution`}
            className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
          >
            <HugeiconsIcon icon={RssIcon} size={16} />
            Distribution
          </a>
        </nav>

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
            icon={<HugeiconsIcon icon={InboxIcon} size={64} />}
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
