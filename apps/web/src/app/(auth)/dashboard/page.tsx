"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { projectSchema, type ProjectFormData } from "@/lib/validation"

interface Project {
  id: string
  title: string
  description: string | null
  episode_count: number
  created_at: string
}

export default function DashboardPage() {
  const router = useRouter()
  const { data: session, status } = useSession()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
  } = useForm<ProjectFormData>({
    resolver: zodResolver(projectSchema),
    mode: "onBlur",
  })

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login")
    } else if (status === "authenticated") {
      loadProjects()
    }
  }, [status])

  const loadProjects = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        headers: {
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setProjects(data.items || [])
      }
    } catch (error) {
      console.error("Failed to load projects:", error)
    } finally {
      setLoading(false)
    }
  }

  const createProject = async (data: ProjectFormData) => {
    setIsSubmitting(true)
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${(session as any)?.accessToken}`,
        },
        body: JSON.stringify({
          title: data.title,
          description: data.description,
          podcast_metadata: {
            language: "en",
            explicit: false,
          },
        }),
      })

      if (response.ok) {
        setShowCreateDialog(false)
        reset()
        loadProjects()
      }
    } catch (error) {
      console.error("Failed to create project:", error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDialogOpenChange = (open: boolean) => {
    setShowCreateDialog(open)
    if (!open) reset()
  }

  if (loading) {
    return <div className="p-8">Loading...</div>
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">My Projects</h1>
          <Button onClick={() => setShowCreateDialog(true)}>
            Create Project
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => (
            <Card
              key={project.id}
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => router.push(`/projects/${project.id}`)}
            >
              <CardHeader>
                <CardTitle>{project.title}</CardTitle>
                <CardDescription>
                  {project.description || "No description"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-600">
                  {project.episode_count} episode{project.episode_count !== 1 ? "s" : ""}
                </p>
              </CardContent>
            </Card>
          ))}

          {projects.length === 0 && (
            <Card className="col-span-full">
              <CardContent className="py-12 text-center">
                <p className="text-gray-600 mb-4">No projects yet</p>
                <Button onClick={() => setShowCreateDialog(true)}>
                  Create Your First Project
                </Button>
              </CardContent>
            </Card>
          )}
        </div>

        <Dialog open={showCreateDialog} onOpenChange={handleDialogOpenChange}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Project</DialogTitle>
              <DialogDescription>
                Create a new podcast project to organize your episodes
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(createProject)} className="space-y-4 mt-4">
              <div>
                <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">
                  Project Title <span className="text-red-500">*</span>
                </label>
                <Input
                  id="title"
                  placeholder="My Podcast"
                  aria-invalid={errors.title ? "true" : "false"}
                  className={errors.title ? "border-red-500" : ""}
                  {...register("title")}
                />
                {errors.title && (
                  <p className="text-red-500 text-sm mt-1">{errors.title.message}</p>
                )}
              </div>
              <div>
                <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <Input
                  id="description"
                  placeholder="A brief description of your podcast"
                  {...register("description")}
                />
                {errors.description && (
                  <p className="text-red-500 text-sm mt-1">{errors.description.message}</p>
                )}
                <p className="text-gray-500 text-xs mt-1">Max 1000 characters</p>
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
      </div>
    </div>
  )
}
