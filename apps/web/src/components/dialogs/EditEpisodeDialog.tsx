"use client"

import * as React from "react"
import { useState, useEffect } from "react"
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

interface Episode {
  id: string
  title: string
  description: string | null
  generation_status: string
  created_at: string
}

interface EditEpisodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  episode: Episode
  onUpdate: (updated: Episode) => void
  onSave: (data: { title: string; description: string }) => Promise<void>
  isLoading?: boolean
}

export function EditEpisodeDialog({
  open,
  onOpenChange,
  episode,
  onUpdate,
  onSave,
  isLoading = false,
}: EditEpisodeDialogProps) {
  const [title, setTitle] = useState(episode.title)
  const [description, setDescription] = useState(episode.description ?? "")

  useEffect(() => {
    if (open) {
      setTitle(episode.title)
      setDescription(episode.description ?? "")
    }
  }, [open, episode])

  const handleSubmit = async () => {
    await onSave({ title, description })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Episode</DialogTitle>
          <DialogDescription>Update the episode details below.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div>
            <Label htmlFor="episode-title">Title</Label>
            <Input
              id="episode-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Episode title"
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="episode-description">Description</Label>
            <Input
              id="episode-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Episode description"
              className="mt-1"
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isLoading || title.trim() === ""}
          >
            {isLoading ? "Updating..." : "Update"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
