"use client"

import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { episodeSchema, type EpisodeFormData } from "@/lib/validation"

interface Episode {
  id: string
  title: string
  description?: string | null
}

interface EditEpisodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  episode: Episode
  onUpdate: (updated: Episode) => void
}

export function EditEpisodeDialog({
  open,
  onOpenChange,
  episode,
  onUpdate,
}: EditEpisodeDialogProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<EpisodeFormData>({
    resolver: zodResolver(episodeSchema),
    mode: "onChange",
    defaultValues: {
      title: episode.title,
    },
  })

  useEffect(() => {
    if (open) {
      reset({ title: episode.title })
    }
  }, [open, episode, reset])

  const onSubmit = async (data: EpisodeFormData) => {
    await onUpdate({
      ...episode,
      title: data.title.trim(),
    })
  }

  const handleOpenChange = (open: boolean) => {
    onOpenChange(open)
    if (!open) {
      reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Episode</DialogTitle>
          <DialogDescription>Update the episode title</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <div>
            <Label htmlFor="edit-episode-title" className="mb-1">
              Episode Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="edit-episode-title"
              type="text"
              placeholder="Episode 1: Introduction"
              aria-invalid={errors.title ? "true" : "false"}
              aria-describedby={errors.title ? "edit-episode-title-error" : undefined}
              {...register("title")}
              className={errors.title ? "border-destructive" : ""}
            />
            {errors.title && (
              <p id="edit-episode-title-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.title.message}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || !isValid}
            >
              {isSubmitting ? "Updating..." : "Update"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
