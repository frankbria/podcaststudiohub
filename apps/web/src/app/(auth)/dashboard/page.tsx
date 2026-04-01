"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useSession, type Session } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

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
  const [newProjectTitle, setNewProjectTitle] = useState("")
  const [newProjectDescription, setNewProjectDescription] = useState("")

  const getToken = useCallback(
    () => (session as Session & { accessToken?: string })?.accessToken ?? "",
    [session]
  )

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      })

      if (response.ok) {
        const data = await response.json() as { items?: Project[] }
        setProjects(data.items ?? [])
      }
    } catch (error) {
      console.error("Failed to load projects:", error)
    } finally {
      setLoading(false)
    }
  }, [getToken])

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login")
    } else if (status === "authenticated") {
      loadProjects()
    }
  }, [status, router, loadProjects])

  const createProject = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          title: newProjectTitle,
          description: newProjectDescription,
          podcast_metadata: {
            language: "en",
            explicit: false,
          },
        }),
      })

      if (response.ok) {
        setShowCreateDialog(false)
        setNewProjectTitle("")
        setNewProjectDescription("")
        loadProjects()
      }
    } catch (error) {
      console.error("Failed to create project:", error)
    }
  }

  if (loading) {
    return <div className="p-8" role="status" aria-live="polite">Loading...</div>
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

        <section aria-label="Projects">
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
                  <CardTitle>{project.title}</CardTitle>
                  <CardDescription>
                    {project.description || "No description"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {project.episode_count} episode{project.episode_count !== 1 ? "s" : ""}
                  </p>
                </CardContent>
              </Card>
            ))}

            {projects.length === 0 && (
              <Card className="col-span-full">
                <CardContent className="py-12 text-center">
                  <p className="text-muted-foreground mb-4">No projects yet</p>
                  <Button onClick={() => setShowCreateDialog(true)}>
                    Create Your First Project
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </section>

        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogContent aria-describedby="create-project-description">
            <DialogHeader>
              <DialogTitle>Create New Project</DialogTitle>
              <DialogDescription id="create-project-description">
                Create a new podcast project to organize your episodes
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <Label htmlFor="project-title" className="mb-1">
                  Project Title
                </Label>
                <Input
                  id="project-title"
                  value={newProjectTitle}
                  onChange={(e) => setNewProjectTitle(e.target.value)}
                  placeholder="My Podcast"
                  aria-required="true"
                />
              </div>
              <div>
                <Label htmlFor="project-description" className="mb-1">
                  Description
                </Label>
                <Input
                  id="project-description"
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                  placeholder="A brief description of your podcast"
                />
              </div>
              <Button onClick={createProject} className="w-full">
                Create Project
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
