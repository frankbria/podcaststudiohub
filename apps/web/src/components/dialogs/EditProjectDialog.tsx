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
import { projectSchema, type ProjectFormData } from "@/lib/validation"

export interface Project {
  id: string
  title: string
  description: string | null
}

interface EditProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project: Project
  onUpdate: (updated: Project) => void
}

export function EditProjectDialog({
  open,
  onOpenChange,
  project,
  onUpdate,
}: EditProjectDialogProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<ProjectFormData>({
    resolver: zodResolver(projectSchema),
    mode: "onChange",
    defaultValues: {
      title: project.title,
      description: project.description ?? "",
    },
  })

  useEffect(() => {
    if (open) {
      reset({
        title: project.title,
        description: project.description ?? "",
      })
    }
  }, [open, project, reset])

  const onSubmit = async (data: ProjectFormData) => {
    await onUpdate({
      ...project,
      title: data.title.trim(),
      description: data.description?.trim() || null,
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
          <DialogTitle>Edit Project</DialogTitle>
          <DialogDescription>Update the project title and description</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <div>
            <Label htmlFor="edit-project-title" className="mb-1">
              Project Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="edit-project-title"
              type="text"
              placeholder="My Podcast"
              aria-invalid={errors.title ? "true" : "false"}
              aria-describedby={errors.title ? "edit-project-title-error" : undefined}
              {...register("title")}
              className={errors.title ? "border-destructive" : ""}
            />
            {errors.title && (
              <p id="edit-project-title-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.title.message}
              </p>
            )}
          </div>
          <div>
            <Label htmlFor="edit-project-description" className="mb-1">
              Description
            </Label>
            <Input
              id="edit-project-description"
              type="text"
              placeholder="A brief description of your podcast"
              aria-describedby={errors.description ? "edit-project-description-error" : undefined}
              {...register("description")}
            />
            {errors.description && (
              <p id="edit-project-description-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.description.message}
              </p>
            )}
            <p className="text-muted-foreground text-xs mt-1">Max 1000 characters</p>
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
