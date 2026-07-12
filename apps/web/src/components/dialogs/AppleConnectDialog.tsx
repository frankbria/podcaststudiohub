"use client"

import { useEffect, useState } from "react"
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
import { appleDistributionSchema, type AppleDistributionFormData } from "@/lib/validation"
import { showErrorToast } from "@/lib/toast"
import { HugeiconsIcon } from "@hugeicons/react"
import { AppleIcon } from "@hugeicons/core-free-icons"

interface AppleAuthorizeInfo {
  message: string
  podcasts_connect_url: string
  setup_instructions: string
}

interface AppleConnectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConnected: () => void
}

export function AppleConnectDialog({ open, onOpenChange, onConnected }: AppleConnectDialogProps) {
  const [instructions, setInstructions] = useState<AppleAuthorizeInfo | null>(null)
  const [loadingInstructions, setLoadingInstructions] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
    reset,
  } = useForm<AppleDistributionFormData>({
    resolver: zodResolver(appleDistributionSchema),
    mode: "onChange",
  })

  useEffect(() => {
    if (!open) return
    reset()
    setInstructions(null)
    setLoadingInstructions(true)

    const loadInstructions = async () => {
      try {
        const response = await fetch("/api/proxy/distribution-targets/apple/authorize", {
          method: "POST",
        })
        if (response.ok) {
          setInstructions((await response.json()) as AppleAuthorizeInfo)
        } else {
          showErrorToast("Failed to load Apple Podcasts setup instructions")
        }
      } catch (error) {
        console.error("Failed to load Apple Podcasts setup instructions:", error)
        showErrorToast("Failed to load Apple Podcasts setup instructions: Network error")
      } finally {
        setLoadingInstructions(false)
      }
    }

    loadInstructions()
  }, [open, reset])

  const onSubmit = async (data: AppleDistributionFormData) => {
    try {
      const response = await fetch("/api/proxy/distribution-targets/apple", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          show_id: data.showId.trim(),
          api_key: data.apiKey,
        }),
      })

      if (response.ok) {
        reset()
        onConnected()
        onOpenChange(false)
      } else {
        // Surface the backend's validation message (e.g. 422 detail) when present.
        const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
        const detail = typeof body?.detail === "string" ? body.detail : response.statusText
        showErrorToast("Failed to connect Apple Podcasts: " + detail)
      }
    } catch (error) {
      console.error("Failed to connect Apple Podcasts:", error)
      showErrorToast("Failed to connect Apple Podcasts: Network error")
    }
  }

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen)
    if (!nextOpen) {
      reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={AppleIcon} size={20} />
            Connect Apple Podcasts
          </DialogTitle>
          <DialogDescription>
            Apple Podcasts ingests episodes from your project&apos;s public RSS feed —
            connecting your account here records a distribution target, it does not directly
            upload episodes.
          </DialogDescription>
        </DialogHeader>

        {loadingInstructions && (
          <p className="text-sm text-muted-foreground">Loading setup instructions...</p>
        )}

        {instructions && (
          <div className="rounded-md border border-border bg-muted p-3 text-sm space-y-2">
            <p>{instructions.message}</p>
            <div className="flex flex-col gap-1">
              {/* setup_instructions is a URL to Apple's help doc, not prose */}
              <a
                href={instructions.setup_instructions}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline"
              >
                View setup instructions
              </a>
              <a
                href={instructions.podcasts_connect_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline"
              >
                Open Apple Podcasts Connect
              </a>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 mt-4" noValidate>
          <div>
            <Label htmlFor="apple-show-id" className="mb-1">
              Show ID <span className="text-destructive">*</span>
            </Label>
            <Input
              id="apple-show-id"
              type="text"
              placeholder="1234567890"
              aria-invalid={errors.showId ? "true" : "false"}
              aria-describedby={errors.showId ? "apple-show-id-error" : undefined}
              {...register("showId")}
              className={errors.showId ? "border-destructive" : ""}
            />
            {errors.showId && (
              <p id="apple-show-id-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.showId.message}
              </p>
            )}
          </div>
          <div>
            <Label htmlFor="apple-api-key" className="mb-1">
              API Key <span className="text-destructive">*</span>
            </Label>
            <Input
              id="apple-api-key"
              type="password"
              placeholder="Apple Podcasts Connect API key"
              aria-invalid={errors.apiKey ? "true" : "false"}
              aria-describedby={errors.apiKey ? "apple-api-key-error" : undefined}
              {...register("apiKey")}
              className={errors.apiKey ? "border-destructive" : ""}
            />
            {errors.apiKey && (
              <p id="apple-api-key-error" className="text-destructive text-sm mt-1" role="alert">
                {errors.apiKey.message}
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
              {isSubmitting ? "Connecting..." : "Connect"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
