"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter, useParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { useForm, type UseFormRegister } from "react-hook-form"
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

// Backend calls go through the same-origin /api/proxy handler, which injects
// the bearer token server-side from the httpOnly cookie — no client token (#212).
// Both return null when the request failed; the error toast has already been shown.
async function fetchProject(projectId: string): Promise<Project | null> {
  try {
    const response = await fetch(`/api/proxy/projects/${projectId}`)
    if (!response.ok) {
      showErrorToast("Failed to load project")
      return null
    }
    // API returns `name`; map to this view-model's `title` (issue #337).
    const data = await response.json() as { id: string; name: string; description: string | null }
    return { id: data.id, title: data.name, description: data.description }
  } catch (error) {
    console.error("Failed to load project:", error)
    showErrorToast("Failed to load project: Network error")
    return null
  }
}

interface EpisodeListResponse {
  episodes?: ApiEpisode[]
}

type ApiEpisode = {
  id: string
  episode_metadata?: { title?: string; description?: string | null }
  generation_status: string
  created_at: string
}

// API returns nested episode_metadata; flatten to this view-model's
// title/description (issue #337).
function toEpisode(e: ApiEpisode): Episode {
  const { title = "", description = null } = e.episode_metadata || {}
  return {
    id: e.id,
    title,
    description,
    generation_status: e.generation_status,
    created_at: e.created_at,
  }
}

async function fetchEpisodes(projectId: string): Promise<Episode[] | null> {
  try {
    const response = await fetch(`/api/proxy/episodes?project_id=${projectId}`)
    if (!response.ok) {
      showErrorToast("Failed to load episodes")
      return null
    }
    // API returns {episodes: [...]} (issue #337).
    const { episodes = [] } = await response.json() as EpisodeListResponse
    return episodes.map(toEpisode)
  } catch (error) {
    console.error("Failed to load episodes:", error)
    showErrorToast("Failed to load episodes: Network error")
    return null
  }
}

// One mutating request: the toast on success, the failure toast with the
// status text, or the network-error toast. Returns the response when it was ok.
interface RequestMessages {
  success: string
  failure: string
}

async function sendRequest(url: string, init: RequestInit, messages: RequestMessages): Promise<Response | null> {
  try {
    const response = await fetch(url, init)
    if (response.ok) {
      showSuccessToast(messages.success)
      return response
    }
    showErrorToast(`${messages.failure}: ` + response.statusText)
  } catch (error) {
    console.error(`${messages.failure}:`, error)
    showErrorToast(`${messages.failure}: Network error`)
  }
  return null
}

function jsonRequest(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  }
}

function createEpisodeRequest(projectId: string, title: string) {
  return sendRequest(
    `/api/proxy/episodes`,
    // API stores episode fields under nested episode_metadata (issue #337).
    jsonRequest("POST", { project_id: projectId, episode_metadata: { title: title.trim() } }),
    { success: "Episode created successfully", failure: "Failed to create episode" },
  )
}

function updateProjectRequest(updated: Project) {
  return sendRequest(
    `/api/proxy/projects/${updated.id}`,
    // API exposes PUT for project update (issue #337)
    jsonRequest("PUT", { name: updated.title, description: updated.description }),
    { success: "Project updated", failure: "Failed to update project" },
  )
}

function updateEpisodeRequest(updated: EditableEpisode) {
  return sendRequest(
    `/api/proxy/episodes/${updated.id}`,
    // API exposes PUT for episode update (issue #337)
    jsonRequest("PUT", { episode_metadata: { title: updated.title } }),
    { success: "Episode updated", failure: "Failed to update episode" },
  )
}

function deleteEpisodeRequest(episode: Episode) {
  return sendRequest(
    `/api/proxy/episodes/${episode.id}`,
    { method: "DELETE" },
    { success: "Episode deleted successfully", failure: "Failed to delete episode" },
  )
}

type RouteParams = { id: string }

// The App Router reuses this page's instance when only [id] changes, so its
// state (loading flag, loaded project) would carry over and show the previous
// project until the new fetch lands. Keying on the id remounts it instead (#529).
export default function ProjectPageRoute() {
  const params = useParams<RouteParams>()
  return <ProjectPage key={params.id} />
}

function useProjectData(projectId: string) {
  const { status: authStatus } = useSession()
  const [project, setProject] = useState<Project | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (authStatus !== "authenticated") return
    let ignore = false
    function projectLoaded(loaded: Project | null) {
      if (ignore) return
      if (loaded) setProject(loaded)
      setLoading(false)
    }
    function episodesLoaded(loaded: Episode[] | null) {
      if (!ignore && loaded) setEpisodes(loaded)
    }
    fetchProject(projectId).then(projectLoaded)
    fetchEpisodes(projectId).then(episodesLoaded)
    return () => {
      ignore = true
    }
  }, [authStatus, projectId])

  return { project, setProject, episodes, setEpisodes, loading }
}

function ProjectPage() {
  const router = useRouter()
  const params = useParams<RouteParams>()
  const { project, setProject, episodes, setEpisodes, loading } = useProjectData(params.id)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditProject, setShowEditProject] = useState(false)
  const [editEpisode, setEditEpisode] = useState<Episode | null>(null)
  const [deleteEpisode, setDeleteEpisode] = useState<Episode | null>(null)
  const [isDeletingEpisode, setIsDeletingEpisode] = useState(false)

  const handleUpdateProject = async (updated: Project) => {
    if (!(await updateProjectRequest(updated))) return
    setShowEditProject(false)
    setProject(updated)
  }

  const handleUpdateEpisode = async (updated: EditableEpisode) => {
    if (!(await updateEpisodeRequest(updated))) return
    setEditEpisode(null)
    setEpisodes((prev) => prev.map((e) => withTitle(e, updated)))
  }

  const handleConfirmDeleteEpisode = async () => {
    if (!deleteEpisode) return
    setIsDeletingEpisode(true)
    const deleted = await deleteEpisodeRequest(deleteEpisode)
    if (deleted) {
      setDeleteEpisode(null)
      setEpisodes((prev) => prev.filter((e) => e.id !== deleteEpisode.id))
    }
    setIsDeletingEpisode(false)
  }

  const goToDashboard = () => router.push("/dashboard")
  const openCreateDialog = () => setShowCreateDialog(true)

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
        <Button variant="outline" onClick={goToDashboard} className="mb-4">
          ← Back to Dashboard
        </Button>

        <ProjectSubNav projectId={params.id} />

        <ProjectHeader project={project} onEdit={setShowEditProject} onCreate={openCreateDialog} />

        <EpisodeList
          episodes={episodes}
          onCreate={openCreateDialog}
          onEdit={setEditEpisode}
          onDelete={setDeleteEpisode}
        />

        <CreateEpisodeDialog
          open={showCreateDialog}
          onOpenChange={setShowCreateDialog}
          projectId={params.id}
        />

        {project && (
          <EditProjectDialog
            open={showEditProject}
            onOpenChange={setShowEditProject}
            project={project}
            onUpdate={handleUpdateProject}
          />
        )}

        <EditEpisodeSlot episode={editEpisode} onClose={setEditEpisode} onUpdate={handleUpdateEpisode} />

        <DeleteEpisodeSlot
          episode={deleteEpisode}
          onClose={setDeleteEpisode}
          isLoading={isDeletingEpisode}
          onConfirm={handleConfirmDeleteEpisode}
        />
      </div>
    </div>
  )
}

function withTitle(episode: Episode, updated: EditableEpisode): Episode {
  return episode.id === updated.id ? { ...episode, title: updated.title } : episode
}

interface ProjectSubNavProps {
  projectId: string
}

function ProjectSubNav({ projectId }: ProjectSubNavProps) {
  const linkClass = "flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
  return (
    <nav className="flex gap-4 mb-4">
      <Link href={`/projects/${projectId}/analytics`} className={linkClass}>
        <HugeiconsIcon icon={Analytics01Icon} size={16} />
        Analytics
      </Link>
      <Link href={`/projects/${projectId}/distribution`} className={linkClass}>
        <HugeiconsIcon icon={RssIcon} size={16} />
        Distribution
      </Link>
    </nav>
  )
}

interface ProjectHeaderProps {
  project: Project | null
  onEdit: (open: boolean) => void
  onCreate: () => void
}

function ProjectHeader({ project, onEdit, onCreate }: ProjectHeaderProps) {
  const openEdit = () => onEdit(true)
  return (
    <div className="flex justify-between items-center mb-8">
      <div className="flex items-center gap-2">
        <div>
          <h1 className="text-3xl font-bold">{project?.title}</h1>
          <p className="text-muted-foreground mt-1">{project?.description}</p>
        </div>
        {project && (
          <Button variant="ghost" size="sm" aria-label="Edit project" onClick={openEdit}>
            <HugeiconsIcon icon={PencilEdit01Icon} size={16} />
          </Button>
        )}
      </div>
      <Button onClick={onCreate}>
        Create Episode
      </Button>
    </div>
  )
}

interface EpisodeActions {
  onEdit: (episode: Episode) => void
  onDelete: (episode: Episode) => void
}

interface EpisodeListProps extends EpisodeActions {
  episodes: Episode[]
  onCreate: () => void
}

function EpisodeList({ episodes, onCreate, ...actions }: EpisodeListProps) {
  if (episodes.length === 0) {
    return (
      <EmptyState
        icon={<HugeiconsIcon icon={InboxIcon} size={64} />}
        title="No episodes in this project"
        description="Create an episode to start generating podcasts"
        action={{
          label: "Create Episode",
          onClick: onCreate,
        }}
      />
    )
  }
  const cards = episodes.map((episode) => episodeCard(episode, actions))
  return <div className="space-y-4">{cards}</div>
}

function episodeCard(episode: Episode, actions: EpisodeActions) {
  return (
    <EpisodeCard key={episode.id} episode={episode} onEdit={actions.onEdit} onDelete={actions.onDelete} />
  )
}

interface EpisodeCardProps extends EpisodeActions {
  episode: Episode
}

function EpisodeCard({ episode, onEdit, onDelete }: EpisodeCardProps) {
  const edit = () => onEdit(episode)
  const remove = () => onDelete(episode)
  return (
    <Card className="hover:shadow-lg transition-shadow">
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            {/*
              Only the title links to the episode — the card used to be
              role=button while wrapping the status badge and Edit/Delete
              buttons, which is invalid ARIA (a control nesting controls).
              A next/link on the title alone fixes the nesting (#323).
            */}
            <CardTitle>
              <Link
                href={`/episodes/${episode.id}`}
                aria-label={`Open episode: ${episode.title}`}
                className="rounded hover:underline focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                {episode.title}
              </Link>
            </CardTitle>
            <CardDescription>{episode.description || "No description"}</CardDescription>
          </div>
          <div className="flex items-center gap-1">
            <StatusBadge status={episode.generation_status} />
            <Button variant="ghost" size="sm" aria-label={`Edit ${episode.title}`} onClick={edit}>
              <HugeiconsIcon icon={PencilEdit01Icon} size={16} />
            </Button>
            <Button variant="ghost" size="sm" aria-label={`Delete ${episode.title}`} onClick={remove}>
              <HugeiconsIcon icon={Delete02Icon} size={16} />
            </Button>
          </div>
        </div>
      </CardHeader>
    </Card>
  )
}

const STATUS_COLORS: Record<string, string> = {
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

interface StatusBadgeProps {
  status: string
}

function StatusBadge({ status }: StatusBadgeProps) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.draft
  return (
    <span className={`px-2 py-1 rounded text-xs ${color}`} aria-label={`Status: ${status}`}>
      {status}
    </span>
  )
}

interface CreateEpisodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string
}

function CreateEpisodeDialog({ open, onOpenChange, projectId }: CreateEpisodeDialogProps) {
  const router = useRouter()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<EpisodeFormData>({
    resolver: zodResolver(episodeSchema),
    mode: "onChange",
  })

  const onSubmit = async (data: EpisodeFormData) => {
    const response = await createEpisodeRequest(projectId, data.title)
    if (!response) return
    const episode = await response.json() as Episode
    onOpenChange(false)
    reset()
    router.push(`/episodes/${episode.id}`)
  }

  const handleOpenChange = (next: boolean) => {
    onOpenChange(next)
    if (!next) {
      reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New Episode</DialogTitle>
          <DialogDescription>
            Create a new podcast episode
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <EpisodeTitleField register={register} error={errors.title?.message} />
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
  )
}

interface EpisodeTitleFieldProps {
  register: UseFormRegister<EpisodeFormData>
  error: string | undefined
}

function EpisodeTitleField({ register, error }: EpisodeTitleFieldProps) {
  const invalid = error !== undefined
  return (
    <div>
      <Label htmlFor="episode-title" className="mb-1">
        Episode Title <span className="text-destructive">*</span>
      </Label>
      <Input
        id="episode-title"
        type="text"
        placeholder="Episode 1: Introduction"
        aria-invalid={invalid ? "true" : "false"}
        aria-describedby={invalid ? "episode-title-error" : undefined}
        {...register("title")}
        className={invalid ? "border-destructive" : ""}
      />
      {invalid && (
        <p id="episode-title-error" className="text-destructive text-sm mt-1" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

// Closing either dialog clears the episode it was opened for.
function closeWith(onClose: (episode: null) => void) {
  return (open: boolean) => {
    if (!open) onClose(null)
  }
}

interface EditEpisodeSlotProps {
  episode: Episode | null
  onClose: (episode: null) => void
  onUpdate: (updated: EditableEpisode) => Promise<void>
}

function EditEpisodeSlot({ episode, onClose, onUpdate }: EditEpisodeSlotProps) {
  if (!episode) return null
  return (
    <EditEpisodeDialog open onOpenChange={closeWith(onClose)} episode={episode} onUpdate={onUpdate} />
  )
}

interface DeleteEpisodeSlotProps {
  episode: Episode | null
  onClose: (episode: null) => void
  isLoading: boolean
  onConfirm: () => Promise<void>
}

function DeleteEpisodeSlot({ episode, onClose, isLoading, onConfirm }: DeleteEpisodeSlotProps) {
  if (!episode) return null
  return (
    <ConfirmDeleteDialog
      open
      onOpenChange={closeWith(onClose)}
      title="Delete Episode?"
      description="This will permanently delete the episode and all its content."
      entityName={episode.title}
      isLoading={isLoading}
      onConfirm={onConfirm}
    />
  )
}
