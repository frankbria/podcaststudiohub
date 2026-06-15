"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { projectSchema, type ProjectFormData } from "@/lib/validation"
import { showSuccessToast, showErrorToast } from "@/lib/toast"
import { DashboardSkeleton } from "@/components/skeletons/DashboardSkeleton"
import { EmptyState } from "@/components/empty-state/EmptyState"
import { ConfirmDeleteDialog } from "@/components/dialogs/ConfirmDeleteDialog"
import { EditProjectDialog } from "@/components/dialogs/EditProjectDialog"
import { HugeiconsIcon } from "@hugeicons/react"
import { FolderOpenIcon, PencilEdit01Icon, Delete02Icon } from "@hugeicons/core-free-icons"

interface Project {
  id: string
  title: string
  description: string | null
  episode_count: number
  created_at: string
}

export default function DashboardPage() {
  const router = useRouter()
  const { status } = useSession()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editProject, setEditProject] = useState<Project | null>(null)
  const [deleteProject, setDeleteProject] = useState<Project | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<ProjectFormData>({
    resolver: zodResolver(projectSchema),
    mode: "onChange",
  })

  // Authenticated backend calls go through the same-origin /api/proxy Route
  // Handler, which injects the bearer token server-side from the httpOnly
  // session cookie. The cookie is sent automatically on same-origin requests,
  // so no Authorization header (and no client-side token) is needed (#212).
  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch(`/api/proxy/projects`)

      if (response.ok) {
        const data = await response.json() as { items?: Project[] }
        setProjects(data.items ?? [])
      } else {
        showErrorToast("Failed to load projects")
      }
    } catch (error) {
      console.error("Failed to load projects:", error)
      showErrorToast("Failed to load projects: Network error")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login")
    } else if (status === "authenticated") {
      loadProjects()
    }
  }, [status, router, loadProjects])

  const onSubmit = async (data: ProjectFormData) => {
    try {
      const response = await fetch(`/api/proxy/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title: data.title.trim(),
          description: data.description?.trim() || null,
          podcast_metadata: {
            language: "en",
            explicit: false,
          },
        }),
      })

      if (response.ok) {
        showSuccessToast("Project created successfully")
        setShowCreateDialog(false)
        reset()
        loadProjects()
      } else {
        showErrorToast("Failed to create project: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to create project:", error)
      showErrorToast("Failed to create project: Network error")
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
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            title: updated.title,
            description: updated.description,
          }),
        }
      )

      if (response.ok) {
        showSuccessToast("Project updated")
        setEditProject(null)
        setProjects((prev) =>
          prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p))
        )
      } else {
        showErrorToast("Failed to update project: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to update project:", error)
      showErrorToast("Failed to update project: Network error")
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteProject) return
    setIsDeleting(true)
    try {
      const response = await fetch(
        `/api/proxy/projects/${deleteProject.id}`,
        {
          method: "DELETE",
        }
      )

      if (response.ok) {
        showSuccessToast("Project deleted successfully")
        setDeleteProject(null)
        setProjects((prev) => prev.filter((p) => p.id !== deleteProject.id))
      } else {
        showErrorToast("Failed to delete project: " + response.statusText)
      }
    } catch (error) {
      console.error("Failed to delete project:", error)
      showErrorToast("Failed to delete project: Network error")
    } finally {
      setIsDeleting(false)
    }
  }

  if (loading) {
    return <DashboardSkeleton />
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">My Projects</h1>
          <Button onClick={() => setShowCreateDialog(true)}>
            Create Project
          </Button>
        </div>

        {projects.length === 0 ? (
          <EmptyState
            icon={<HugeiconsIcon icon={FolderOpenIcon} size={64} />}
            title="No projects yet"
            description="Create your first podcast project to get started"
            action={{
              label: "Create Project",
              onClick: () => setShowCreateDialog(true),
            }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects.map((project) => (
              <Card
                key={project.id}
                className="cursor-pointer hover:shadow-lg transition-shadow focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                role="button"
                tabIndex={0}
                aria-label={`Open project: ${project.title}`}
                onClick={() => router.push(`/projects/${project.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    router.push(`/projects/${project.id}`)
                  }
                }}
              >
                <CardHeader>
                  <div className="flex justify-between items-start gap-2">
                    <div className="min-w-0">
                      <CardTitle className="truncate">{project.title}</CardTitle>
                      <CardDescription>
                        {project.description || "No description"}
                      </CardDescription>
                    </div>
                    <div className="flex gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Edit ${project.title}`}
                        onClick={() => setEditProject(project)}
                      >
                        <HugeiconsIcon icon={PencilEdit01Icon} size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Delete ${project.title}`}
                        onClick={() => setDeleteProject(project)}
                      >
                        <HugeiconsIcon icon={Delete02Icon} size={16} />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {project.episode_count} episode{project.episode_count !== 1 ? "s" : ""}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Dialog open={showCreateDialog} onOpenChange={handleDialogOpenChange}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Project</DialogTitle>
              <DialogDescription>
                Create a new podcast project to organize your episodes
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
              <div>
                <Label htmlFor="project-title" className="mb-1">
                  Project Title <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="project-title"
                  type="text"
                  placeholder="My Podcast"
                  aria-invalid={errors.title ? "true" : "false"}
                  aria-describedby={errors.title ? "project-title-error" : undefined}
                  {...register("title")}
                  className={errors.title ? "border-destructive" : ""}
                />
                {errors.title && (
                  <p id="project-title-error" className="text-destructive text-sm mt-1" role="alert">
                    {errors.title.message}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="project-description" className="mb-1">Description</Label>
                <Input
                  id="project-description"
                  type="text"
                  placeholder="A brief description of your podcast"
                  aria-describedby={errors.description ? "project-description-error" : undefined}
                  {...register("description")}
                />
                {errors.description && (
                  <p id="project-description-error" className="text-destructive text-sm mt-1" role="alert">
                    {errors.description.message}
                  </p>
                )}
                <p className="text-muted-foreground text-xs mt-1">Max 1000 characters</p>
              </div>
              <Button
                type="submit"
                disabled={isSubmitting || !isValid}
                className="w-full"
              >
                {isSubmitting ? "Creating..." : "Create Project"}
              </Button>
            </form>
          </DialogContent>
        </Dialog>

        {editProject && (
          <EditProjectDialog
            open={!!editProject}
            onOpenChange={(open) => { if (!open) setEditProject(null) }}
            project={editProject}
            onUpdate={handleUpdateProject}
          />
        )}

        {deleteProject && (
          <ConfirmDeleteDialog
            open={!!deleteProject}
            onOpenChange={(open) => { if (!open) setDeleteProject(null) }}
            title="Delete Project?"
            description="This will permanently delete the project and all its episodes."
            entityName={deleteProject.title}
            isLoading={isDeleting}
            onConfirm={handleConfirmDelete}
          />
        )}
      </div>
    </div>
  )
}
