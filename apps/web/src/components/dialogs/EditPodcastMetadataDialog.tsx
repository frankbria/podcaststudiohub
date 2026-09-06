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
import { Textarea } from "@/components/ui/textarea"
import { podcastMetadataSchema, type PodcastMetadataFormData } from "@/lib/validation"

interface EditPodcastMetadataDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialMetadata?: Partial<PodcastMetadataFormData>
  onSubmitMetadata: (data: PodcastMetadataFormData) => void | Promise<void>
}

const emptyDefaults: PodcastMetadataFormData = {
  showTitle: "",
  author: "",
  description: "",
  category: "",
  language: "",
  explicit: false,
  copyright: "",
  artworkUrl: "",
  websiteUrl: "",
}

export function EditPodcastMetadataDialog({
  open,
  onOpenChange,
  initialMetadata,
  onSubmitMetadata,
}: EditPodcastMetadataDialogProps) {
  const defaultValues: PodcastMetadataFormData = {
    ...emptyDefaults,
    ...initialMetadata,
  }

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<PodcastMetadataFormData>({
    resolver: zodResolver(podcastMetadataSchema),
    mode: "onChange",
    defaultValues,
  })

  useEffect(() => {
    if (open) {
      reset({ ...emptyDefaults, ...initialMetadata })
    }
  }, [open, initialMetadata, reset])

  const onSubmit = async (data: PodcastMetadataFormData) => {
    await onSubmitMetadata({
      ...data,
      showTitle: data.showTitle.trim(),
      author: data.author.trim(),
      description: data.description.trim(),
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
          <DialogTitle>Edit Podcast Metadata</DialogTitle>
          <DialogDescription>
            Update the show metadata used to build your RSS feed
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <div>
            <Label htmlFor="podcast-show-title" className="mb-1">
              Show Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="podcast-show-title"
              type="text"
              placeholder="My Awesome Podcast"
              aria-invalid={errors.showTitle ? "true" : "false"}
              aria-describedby={errors.showTitle ? "podcast-show-title-error" : undefined}
              {...register("showTitle")}
              className={errors.showTitle ? "border-destructive" : ""}
            />
            {errors.showTitle && (
              <p id="podcast-show-title-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.showTitle.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="podcast-author" className="mb-1">
              Author <span className="text-destructive">*</span>
            </Label>
            <Input
              id="podcast-author"
              type="text"
              placeholder="Jane Doe"
              aria-invalid={errors.author ? "true" : "false"}
              aria-describedby={errors.author ? "podcast-author-error" : undefined}
              {...register("author")}
              className={errors.author ? "border-destructive" : ""}
            />
            {errors.author && (
              <p id="podcast-author-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.author.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="podcast-description" className="mb-1">
              Description <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="podcast-description"
              placeholder="A podcast about awesome things"
              aria-invalid={errors.description ? "true" : "false"}
              aria-describedby={errors.description ? "podcast-description-error" : undefined}
              {...register("description")}
              className={errors.description ? "border-destructive" : ""}
            />
            {errors.description && (
              <p id="podcast-description-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.description.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="podcast-category" className="mb-1">
              Category
            </Label>
            <Input
              id="podcast-category"
              type="text"
              placeholder="Technology"
              {...register("category")}
            />
          </div>

          <div>
            <Label htmlFor="podcast-language" className="mb-1">
              Language
            </Label>
            <Input
              id="podcast-language"
              type="text"
              placeholder="en-US"
              {...register("language")}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              id="podcast-explicit"
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              {...register("explicit")}
            />
            <Label htmlFor="podcast-explicit">Explicit content</Label>
          </div>

          <div>
            <Label htmlFor="podcast-copyright" className="mb-1">
              Copyright
            </Label>
            <Input
              id="podcast-copyright"
              type="text"
              placeholder="© 2026 Jane Doe"
              {...register("copyright")}
            />
          </div>

          <div>
            <Label htmlFor="podcast-artwork-url" className="mb-1">
              Artwork URL
            </Label>
            <Input
              id="podcast-artwork-url"
              type="text"
              placeholder="https://example.com/artwork.png"
              aria-invalid={errors.artworkUrl ? "true" : "false"}
              aria-describedby={errors.artworkUrl ? "podcast-artwork-url-error" : undefined}
              {...register("artworkUrl")}
              className={errors.artworkUrl ? "border-destructive" : ""}
            />
            {errors.artworkUrl && (
              <p id="podcast-artwork-url-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.artworkUrl.message}
              </p>
            )}
          </div>

          <div>
            <Label htmlFor="podcast-website-url" className="mb-1">
              Website URL
            </Label>
            <Input
              id="podcast-website-url"
              type="text"
              placeholder="https://example.com"
              aria-invalid={errors.websiteUrl ? "true" : "false"}
              aria-describedby={errors.websiteUrl ? "podcast-website-url-error" : undefined}
              {...register("websiteUrl")}
              className={errors.websiteUrl ? "border-destructive" : ""}
            />
            {errors.websiteUrl && (
              <p id="podcast-website-url-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.websiteUrl.message}
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
            <Button type="submit" disabled={isSubmitting || !isValid}>
              {isSubmitting ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
