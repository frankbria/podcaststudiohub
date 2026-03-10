"use client"

import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export interface EditableProject {
  id: string
  title: string
  description: string | null
}

export interface EditProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project: EditableProject
  onUpdate: (updated: EditableProject) => void
  token: string
}

export function EditProjectDialog({
  open,
  onOpenChange,
  project,
  onUpdate,
  token,
}: EditProjectDialogProps) {
  const [title, setTitle] = React.useState(project.title)
  const [description, setDescription] = React.useState(project.description ?? "")
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setTitle(project.title)
      setDescription(project.description ?? "")
      setError(null)
    }
  }, [open, project])

  const canSubmit = title.trim().length > 0 && !submitting

  const handleSubmit = async () => {
    setError(null)
    setSubmitting(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${project.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ title: title.trim(), description: description.trim() || null }),
        }
      )

      if (!response.ok) {
        let detail = response.statusText
        try {
          const err = await response.json()
          detail = err.detail || detail
        } catch {}
        throw new Error(detail)
      }

      const updated = await response.json()
      onUpdate(updated)
      onOpenChange(false)
    } catch (err: any) {
      setError(`Failed to update project: ${err.message || "Unknown error"}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Project</DialogTitle>
          <DialogDescription>
            Update the project title and description.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-1">
            <Label htmlFor="edit-project-title">Title</Label>
            <Input
              id="edit-project-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Project title"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="edit-project-description">Description</Label>
            <Input
              id="edit-project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Project description (optional)"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? "Updating..." : "Update"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
