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

export interface EditableEpisode {
  id: string
  title: string
  description: string | null
  generation_status: string
  project_id: string
}

export interface EditEpisodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  episode: EditableEpisode
  onUpdate: (updated: EditableEpisode) => void
  token: string
}

export function EditEpisodeDialog({
  open,
  onOpenChange,
  episode,
  onUpdate,
  token,
}: EditEpisodeDialogProps) {
  const [title, setTitle] = React.useState(episode.title)
  const [description, setDescription] = React.useState(episode.description ?? "")
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setTitle(episode.title)
      setDescription(episode.description ?? "")
      setError(null)
    }
  }, [open, episode])

  const canSubmit = title.trim().length > 0 && !submitting

  const handleSubmit = async () => {
    setError(null)
    setSubmitting(true)
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/episodes/${episode.id}`,
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
      setError(`Failed to update episode: ${err.message || "Unknown error"}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Episode</DialogTitle>
          <DialogDescription>
            Update the episode title and description.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-1">
            <Label htmlFor="edit-episode-title">Title</Label>
            <Input
              id="edit-episode-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Episode title"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="edit-episode-description">Description</Label>
            <Input
              id="edit-episode-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Episode description (optional)"
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
